import logging
import uuid as _uuid
from django.db import connection
from api.models import ConversationSession, CampaignContext, CampaignStep, CampaignEmail

logger = logging.getLogger(__name__)


class CampaignService:
    """
    Service for campaign management operations.
    """

    @staticmethod
    def create_campaign(
        session_id: str,
        campaign_name: str = "AI powered",
        creation_mode: str = "ai",
        lead_list_id: str = None,
        search_run_id: str = None
    ) -> dict:
        """
        Create a campaign linked to a search_run_id.
        
        Args:
            session_id: Conversation session ID
            campaign_name: Name for the campaign
            creation_mode: 'ai' or 'manual'
            lead_list_id: Optional lead list ID (not required)
            search_run_id: Optional search run ID (will use from session state if not provided)
            
        Returns:
            dict with campaign_id, status, etc.
            
        Raises:
            ValueError: If session not found or invalid parameters
        """
        try:
            session = ConversationSession.objects.get(session_id=session_id)
        except ConversationSession.DoesNotExist:
            raise ValueError("session not found")

        state = session.state or {}
        search_run_id = search_run_id or state.get("search_run_id")

        # Resolve lead_list_id: explicit param > session state
        lead_list_id = lead_list_id or state.get("lead_list_id")

        # Generate campaign name from slots if not provided
        if campaign_name == "AI powered":
            slots = state.get("slots", {})
            campaign_name = _generate_campaign_name_from_slots(slots)

        # ── Raw SQL insert — campaigns
        # Use UUID without dashes (32-char hex) to match DB char(32) column
        campaign_id = str(_uuid.uuid4()).replace('-', '')
        
        # Get user_id from session if available
        user_id = getattr(session, 'user_id', None) or state.get('user_id')
        
        with connection.cursor() as cursor:
            # Always include lead_list_id column (NULL if not available)
            # Include created_by to track campaign ownership
            cursor.execute(
                """INSERT INTO campaigns (id, org_id, lead_list_id, name, creation_mode, status, created_by, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())""",
                [campaign_id, session.tenant_id, lead_list_id, campaign_name, creation_mode, "ai_clarifying", user_id],
            )

        # ── Persist in session state ─────────────────────────────────────────
        state.update({
            "flow": "campaign_flow",
            "campaign_id": campaign_id,
            "search_run_id": search_run_id,
            "lead_list_id": lead_list_id,
        })
        session.state = state
        session.save(update_fields=["state", "updated_at"])

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "creation_mode": creation_mode,
            "lead_list_id": lead_list_id,
            "search_run_id": search_run_id,
            "status": "ai_clarifying",
        }

    @staticmethod
    def approve_campaign(session_id: str, campaign_id: str = None) -> dict:
        """
        Approve a campaign - sets status to 'approved'.
        
        Args:
            session_id: Conversation session ID
            campaign_id: Optional campaign ID (will use from session state if not provided)
            
        Returns:
            dict with campaign_id, status, lead_list_id
            
        Raises:
            ValueError: If session or campaign not found
        """
        try:
            session = ConversationSession.objects.get(session_id=session_id)
        except ConversationSession.DoesNotExist:
            raise ValueError("session not found")

        state = session.state or {}
        campaign_id = campaign_id or state.get("campaign_id")
        if not campaign_id:
            raise ValueError("campaign_id required")

        # ── Verify campaign exists (handle both with/without dashes) ─────────
        with connection.cursor() as cursor:
            # Try with original format first
            cursor.execute("SELECT id, lead_list_id FROM campaigns WHERE id = %s", [campaign_id])
            row = cursor.fetchone()
            
            # If not found, try without dashes
            if not row:
                campaign_id_no_dashes = campaign_id.replace('-', '')
                cursor.execute("SELECT id, lead_list_id FROM campaigns WHERE id = %s", [campaign_id_no_dashes])
                row = cursor.fetchone()
                if row:
                    campaign_id = campaign_id_no_dashes  # Use the format that exists in DB
            
            if not row:
                raise ValueError(f"Campaign {campaign_id} not found")
            lead_list_id = row[1]

            # ── Update status ────────────────────────────────────────────────
            cursor.execute(
                "UPDATE campaigns SET status = %s, updated_at = NOW() WHERE id = %s",
                ["approved", campaign_id],
            )

        state["campaign_status"] = "approved"
        session.state = state
        session.save(update_fields=["state", "updated_at"])

        return {
            "campaign_id": campaign_id,
            "status": "approved",
            "lead_list_id": lead_list_id,
        }

    @staticmethod
    def get_campaign_sequences(session_id: str = None, campaign_id: str = None) -> dict:
        """
        Get sequence list (steps + emails) for a campaign.
        
        Args:
            session_id: Optional conversation session ID
            campaign_id: Optional campaign ID (will use from session state if not provided)
            
        Returns:
            dict with campaign details, sequence array, confirmed_context
            
        Raises:
            ValueError: If campaign not found or invalid parameters
        """
        # ── Resolve campaign_id from session state if not passed ─────────────
        search_run_id = None
        if session_id and not campaign_id:
            try:
                session = ConversationSession.objects.get(session_id=session_id)
                state = session.state or {}
                campaign_id = state.get("campaign_id")
                search_run_id = state.get("search_run_id")
            except ConversationSession.DoesNotExist:
                pass

        if not campaign_id:
            raise ValueError("campaign_id required")

        # Normalize campaign_id - remove dashes to match DB format
        campaign_id_normalized = campaign_id.replace('-', '') if campaign_id else None

        # ── Get campaign via raw SQL (avoids FK issues) ──────────────────────
        with connection.cursor() as cursor:
            # Try normalized format (without dashes) first
            cursor.execute(
                "SELECT id, name, status, lead_list_id FROM campaigns WHERE id = %s",
                [campaign_id_normalized],
            )
            row = cursor.fetchone()
            
            # If not found, try original format
            if not row and campaign_id != campaign_id_normalized:
                cursor.execute(
                    "SELECT id, name, status, lead_list_id FROM campaigns WHERE id = %s",
                    [campaign_id],
                )
                row = cursor.fetchone()
                if row:
                    campaign_id_normalized = campaign_id
            
            if not row:
                raise ValueError(f"Campaign {campaign_id} not found")
            
            campaign_id_db = row[0]  # Use actual ID from DB
            campaign_name = row[1]
            campaign_status = row[2]
            lead_list_id = row[3]

        # ── Get search_run_id from session if not resolved yet ───────────────
        if not search_run_id and session_id:
            try:
                session = ConversationSession.objects.get(session_id=session_id)
                search_run_id = (session.state or {}).get("search_run_id")
            except ConversationSession.DoesNotExist:
                pass

        # ── Build sequence (steps + emails) ──────────────────────────────────
        steps = CampaignStep.objects.filter(campaign_id=campaign_id_db).order_by("step_order")
        sequence = []
        for step in steps:
            step_data = {
                "step_id": str(step.id),
                "step_order": step.step_order,
                "delay_days": step.delay_days,
                "condition": step.condition,
            }
            try:
                email = step.email
                step_data["email"] = {
                    "email_id": str(email.id),
                    "subject": email.subject,
                    "body": email.body,
                    "origin": email.origin,
                    "spam_status": email.spam_status,
                }
            except CampaignEmail.DoesNotExist:
                step_data["email"] = None
            sequence.append(step_data)

        # ── Get confirmed_context from campaign_contexts ─────────────────────
        confirmed_context = {}
        try:
            ctx = CampaignContext.objects.get(campaign_id=campaign_id_db)
            confirmed_context = ctx.context_json or {}
        except CampaignContext.DoesNotExist:
            pass

        # ── Transform sequence to match desired format ───────────────────────
        formatted_steps = []
        for step_data in sequence:
            formatted_step = {
                "step_id": step_data["step_id"],
                "step_order": step_data["step_order"],
                "delay_days": step_data["delay_days"],
                "step_condition": step_data["condition"],
            }
            
            # Transform email format
            if step_data.get("email"):
                email = step_data["email"]
                formatted_step["email"] = {
                    "id": email["email_id"],
                    "subject": email["subject"],
                    "body": email["body"],
                    "spam_status": email.get("spam_status", "pending"),
                }
            
            formatted_steps.append(formatted_step)

        return {
            "success": True,
            "data": {
                "campaign_id": campaign_id_db,
                "campaign_status": campaign_status,
                "steps": formatted_steps,
            }
        }


def _generate_campaign_name_from_slots(slots: dict) -> str:
    """Helper function to generate campaign name from ICP slots."""
    parts = []
    
    # Add person location (city/state)
    person_locations = slots.get("person_locations", [])
    if person_locations and isinstance(person_locations, list) and len(person_locations) > 0:
        # Extract just city or state name (e.g., "California, US" -> "California")
        location = person_locations[0].split(',')[0].strip()
        parts.append(location)
    
    # Add organization location as fallback
    if not parts:
        org_locations = slots.get("organization_locations", [])
        if org_locations and isinstance(org_locations, list) and len(org_locations) > 0:
            location = org_locations[0].split(',')[0].strip()
            parts.append(location)
    
    # Add keywords (industry/sector)
    keywords = slots.get("q_keywords", [])
    if keywords and isinstance(keywords, list) and len(keywords) > 0:
        # Take first keyword and clean it up
        keyword = keywords[0].replace("saas applications", "SaaS").replace("software as a service (saas)", "SaaS")
        if len(keyword) < 20:  # Only add if not too long
            parts.append(keyword.title())
    
    # Add person title/role
    person_titles = slots.get("person_titles", [])
    if person_titles and isinstance(person_titles, list) and len(person_titles) > 0:
        # Take first title and simplify
        title = person_titles[0].replace("director of marketing", "Marketing Directors")
        title = title.replace("marketing director", "Marketing Directors")
        title = title.replace("marketing manager", "Marketing Managers")
        title = title.title()
        parts.append(title)
    
    # Build name
    if parts:
        # Limit to 3 parts max for readability
        campaign_name = " ".join(parts[:3]) + " Campaign"
        return campaign_name
    
    # Fallback with timestamp to ensure uniqueness
    import datetime
    timestamp = datetime.datetime.now().strftime("%b %d")
    return f"AI Campaign {timestamp}"

