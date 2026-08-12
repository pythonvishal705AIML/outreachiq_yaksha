from django.db import transaction
from django.db.models import Max

from api.models import ConversationSession, SearchRun, SearchRunLead
from agent_runtime.persistence.models import (
    AgentConversationEvent,
    AgentConversationSession,
    AgentConversationState,
    AgentSourceExecutionAudit,
)


class AgentRepository:
    @staticmethod
    def ensure_session(session_id: str, tenant_id: str) -> AgentConversationSession:
        session, _ = AgentConversationSession.objects.get_or_create(
            session_id=session_id,
            defaults={"tenant_id": tenant_id},
        )
        AgentConversationState.objects.get_or_create(session=session)
        return session

    @staticmethod
    @transaction.atomic
    def log_event(session_id: str, turn_id: str, event_type: str, actor: str, payload: dict):
        session = AgentConversationSession.objects.get(session_id=session_id)
        last_seq = (
            AgentConversationEvent.objects.filter(session=session, turn_id=turn_id)
            .aggregate(mx=Max("seq_no"))
            .get("mx")
            or 0
        )
        return AgentConversationEvent.objects.create(
            session=session,
            turn_id=turn_id,
            seq_no=last_seq + 1,
            event_type=event_type,
            actor=actor,
            payload_json=payload or {},
        )

    @staticmethod
    def update_state(session_id: str, state_json: dict):
        session = AgentConversationSession.objects.get(session_id=session_id)
        state_row, _ = AgentConversationState.objects.get_or_create(session=session)
        state_row.state_json = state_json or {}
        state_row.save(update_fields=["state_json", "updated_at"])

    @staticmethod
    def reset_state(session_id: str):
        try:
            session = AgentConversationSession.objects.get(session_id=session_id)
        except AgentConversationSession.DoesNotExist:
            return
        AgentConversationState.objects.update_or_create(session=session, defaults={"state_json": {}})

    @staticmethod
    def log_source_execution(
        session_id: str,
        provider: str,
        request_payload: dict,
        response_count: int,
        status: str = "completed",
    ):
        session = AgentConversationSession.objects.get(session_id=session_id)
        return AgentSourceExecutionAudit.objects.create(
            session=session,
            provider=provider,
            request_payload=request_payload or {},
            response_count=response_count,
            status=status,
        )

    @staticmethod
    def get_full_history(session_id: str):
        try:
            base_session = ConversationSession.objects.get(session_id=session_id)
        except ConversationSession.DoesNotExist:
            return None

        events = []
        audits = []
        state = base_session.state or {}

        try:
            session = AgentConversationSession.objects.get(session_id=session_id)
            events = [
                {
                    "turn_id": row.turn_id,
                    "seq_no": row.seq_no,
                    "event_type": row.event_type,
                    "actor": row.actor,
                    "payload": row.payload_json,
                    "created_at": row.created_at,
                }
                for row in session.events.order_by("created_at", "turn_id", "seq_no")
            ]
            audits = [
                {
                    "provider": row.provider,
                    "request_payload": row.request_payload,
                    "response_count": row.response_count,
                    "status": row.status,
                    "created_at": row.created_at,
                }
                for row in session.source_audits.order_by("created_at")
            ]
            if hasattr(session, "state_row"):
                state = session.state_row.state_json
        except AgentConversationSession.DoesNotExist:
            pass

        messages = [
            {
                "role": msg.role,
                "text": msg.text,
                "timestamp": msg.timestamp,
                "metadata": msg.metadata if msg.metadata else {},
            }
            for msg in base_session.messages.order_by("timestamp")
        ]

        search_runs = []
        run_ids = []
        for event in events:
            payload = event.get("payload") or {}
            run_id = payload.get("search_run_id")
            if run_id:
                run_ids.append(str(run_id))
        unique_run_ids = list(dict.fromkeys(run_ids))
        if unique_run_ids:
            for run in SearchRun.objects.filter(search_id__in=unique_run_ids).order_by("created_at"):
                leads = (
                    SearchRunLead.objects.select_related("lead")
                    .filter(search_run=run)
                    .order_by("-created_at")[:10]
                )
                leads_summary = [
                    {
                        "lead_id": row.lead.id,
                        "name": row.lead.person_full_name or " ".join(
                            [v for v in [row.lead.first_name, row.lead.last_name] if v]
                        ).strip(),
                        "title": row.lead.title,
                        "company": row.lead.company_name,
                        "email": row.lead.email,
                        "linkedin_url": row.lead.linkedin_url,
                    }
                    for row in leads
                ]
                search_runs.append(
                    {
                        "search_run_id": run.search_id,
                        "created_at": run.created_at,
                        "lead_count": run.lead_count,
                        "source_used": run.source_used,
                        "filters_json": run.filters_json,
                        "query_text": run.query_text,
                        "status_url": f"/api/leads/search/status/{run.search_id}/",
                        "full_results_url": f"/api/leads/search/runs/{run.search_id}/leads/",
                        "leads_preview": leads_summary,
                    }
                )

        return {
            "session_id": session_id,
            "state": state,
            "messages": messages,
            "events": events,
            "source_audits": audits,
            "search_runs": search_runs,
        }
