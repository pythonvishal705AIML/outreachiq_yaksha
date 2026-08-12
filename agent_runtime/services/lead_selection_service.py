import json
import logging
import math
from django.db import connection
from api.models import ConversationSession, LeadList, SearchRun

logger = logging.getLogger(__name__)


class LeadSelectionService:
    """
    Service for selecting leads from search runs and creating lead lists.
    Uses the existing ``lead_lists`` table (Django LeadList model) so no
    extra migration is required.
    """

    @staticmethod
    def select_leads_and_create_list(
        session_id: str,
        search_run_id: str = None,
        selection_percent: int = 100,
        explicit_lead_ids: list = None,
    ) -> dict:
        """
        Select leads from a search run (by % or explicit IDs), create a
        LeadList row, point the selected leads at that list, and persist
        everything in session state for downstream campaign / send flows.
        """
        # ── Resolve session ───────────────────────────────────────────────────
        try:
            session = ConversationSession.objects.get(session_id=session_id)
        except ConversationSession.DoesNotExist:
            raise ValueError("session not found")

        state = session.state or {}

        # ── Resolve search_run_id ─────────────────────────────────────────────
        if not search_run_id:
            search_run_id = state.get("search_run_id")
        if not search_run_id:
            raise ValueError(
                "search_run_id required (pass it or run people search first)"
            )

        try:
            run = SearchRun.objects.get(search_id=search_run_id)
        except SearchRun.DoesNotExist:
            raise ValueError(f"SearchRun {search_run_id} not found")

        # ── Resolve selected lead IDs ─────────────────────────────────────────
        if explicit_lead_ids:
            selected_ids = [str(lid) for lid in explicit_lead_ids]
        else:
            # Primary path: M2M through SearchRunLead
            all_lead_ids = list(
                run.leads.order_by("search_run_leads__created_at")
                .values_list("id", flat=True)
            )

            # Fallback: query leads by last_search_run_id
            if not all_lead_ids:
                logger.warning(
                    "No leads via M2M for SearchRun %s — "
                    "falling back to last_search_run_id",
                    search_run_id,
                )
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM leads "
                        "WHERE last_search_run_id = %s ORDER BY created_at",
                        [search_run_id],
                    )
                    all_lead_ids = [row[0] for row in cur.fetchall()]

            if not all_lead_ids:
                raise ValueError(
                    f"No leads found in search run {search_run_id}. "
                    "The search may not have returned results."
                )

            count = max(
                1, math.ceil(len(all_lead_ids) * selection_percent / 100)
            )
            selected_ids = [str(lid) for lid in all_lead_ids[:count]]

        if not selected_ids:
            raise ValueError("No leads selected")

        # ── Create a LeadList via ORM (uses existing `lead_lists` table) ──────
        list_name = f"Agent List {session_id[:8]} ({selection_percent}%)"
        lead_list = LeadList.objects.create(
            name=list_name,
            description=json.dumps({
                "org_id": session.tenant_id,
                "search_run_id": search_run_id,
                "selection_percent": selection_percent,
                "lead_count": len(selected_ids),
            }),
        )
        lead_list_id = str(lead_list.id)  # integer PK -> string for state

        # ── Point selected leads at this list (makes send-to-leads fallback work)
        if selected_ids:
            placeholders = ",".join(["%s"] * len(selected_ids))
            with connection.cursor() as cur:
                cur.execute(
                    f"UPDATE leads SET lead_list_id = %s "
                    f"WHERE id IN ({placeholders})",
                    [lead_list.id] + selected_ids,
                )
            logger.info(
                "Updated %d leads -> lead_list_id=%s", len(selected_ids), lead_list_id,
            )

        logger.info(
            "Lead list created: id=%s, name=%s, leads=%d, search_run=%s",
            lead_list_id, list_name, len(selected_ids), search_run_id,
        )

        # ── Persist in session state ──────────────────────────────────────────
        state.update({
            "search_run_id": search_run_id,
            "lead_list_id": lead_list_id,
            "selected_lead_ids": selected_ids,
            "selection_percent": selection_percent,
        })
        session.state = state
        session.save(update_fields=["state", "updated_at"])

        return {
            "lead_list_id": lead_list_id,
            "lead_list_name": list_name,
            "selected_count": len(selected_ids),
            "selection_percent": selection_percent,
            "search_run_id": search_run_id,
        }