import logging
import math
import uuid as _uuid

from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import (
    Campaign,
    CampaignContext,
    CampaignEmail,
    CampaignStep,
    ConversationSession,
    SearchRun,
)
from api.services.main_service import APIService
from agent_runtime.mapping.response_mapper import map_message_result
from agent_runtime.orchestrator.turn_manager import TurnManager
from agent_runtime.persistence.repository import AgentRepository
from agent_runtime.tools.lead_source_router import LeadSourceRouter
from agent_runtime.services.lead_selection_service import LeadSelectionService
from agent_runtime.services.campaign_service import CampaignService

logger = logging.getLogger(__name__)


def _is_rollout_enabled_for_session(session_id: str) -> bool:
    if not getattr(settings, "AGENT_RUNTIME_ENABLED", True):
        return False
    allowlist = getattr(settings, "AGENT_RUNTIME_TENANT_ALLOWLIST", []) or []
    if not allowlist:
        return True
    try:
        session = ConversationSession.objects.get(session_id=session_id)
        return session.tenant_id in allowlist
    except ConversationSession.DoesNotExist:
        return False


class AgentConversationInitView(APIView):
    def post(self, request):
        tenant_id = request.data.get("tenant_id") or request.data.get("org_id")
        initial_text = request.data.get("text", "").strip()
        if not tenant_id:
            return Response({"error": "tenant_id or org_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        session_id = APIService.init_conversation_session(tenant_id, initial_text)
        AgentRepository.ensure_session(session_id=session_id, tenant_id=tenant_id)
        
        # Store user_id in session state for campaign ownership tracking
        user = _resolve_user(request)
        if user:
            try:
                session = ConversationSession.objects.get(session_id=session_id)
                state = session.state or {}
                state['user_id'] = user.id
                session.state = state
                session.save(update_fields=['state', 'updated_at'])
                logger.info(f"Stored user_id {user.id} in session {session_id}")
            except ConversationSession.DoesNotExist:
                logger.warning(f"Session {session_id} not found when trying to store user_id")
        
        return Response({"session_id": session_id, "message": "Conversation initialized"}, status=status.HTTP_201_CREATED)


class AgentConversationMessageView(APIView):
    def post(self, request):
        session_id = request.data.get("session_id")
        user_text = request.data.get("text", "").strip()
        if not session_id:
            return Response({"error": "session_id is missing"}, status=status.HTTP_400_BAD_REQUEST)
        if not user_text:
            return Response({"error": "text is missing"}, status=status.HTTP_400_BAD_REQUEST)
        if not _is_rollout_enabled_for_session(session_id):
            return Response({"error": "agent runtime is not enabled for this tenant"}, status=status.HTTP_403_FORBIDDEN)

        try:
            result = TurnManager(session_id=session_id).run_message_turn(user_text=user_text)
            return Response(map_message_result(result), status=status.HTTP_200_OK)
        except ConversationSession.DoesNotExist:
            return Response({"error": "session not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("Agent conversation message failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AgentConversationHistoryView(APIView):
    def post(self, request):
        session_id = request.data.get("session_id")
        if not session_id:
            return Response({"error": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        history = AgentRepository.get_full_history(session_id)
        if history is None:
            return Response({"error": "Invalid session_id"}, status=status.HTTP_404_NOT_FOUND)
        return Response(history, status=status.HTTP_200_OK)


class AgentConversationResetView(APIView):
    def post(self, request):
        session_id = request.data.get("session_id")
        if not session_id:
            return Response({"error": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        APIService.reset_conversation_session(session_id)
        AgentRepository.reset_state(session_id)
        return Response({"message": "Conversation state reset"}, status=status.HTTP_200_OK)


class AgentPeopleSearchView(APIView):
    def post(self, request):
        session_id = request.data.get("session_id")
        params = request.data.get("params") or {}
        channel = request.data.get("channel")  # No external provider configured by default
        account_id = request.data.get("account_id")

        if session_id and not params:
            try:
                session = ConversationSession.objects.get(session_id=session_id)
                slots = (session.state or {}).get("slots", {})
                if slots:
                    params = dict(slots)
                if not account_id:
                    account_id = session.tenant_id
            except ConversationSession.DoesNotExist:
                pass
        params["page"] = request.data.get("page", 1)
        params["per_page"] = request.data.get("per_page", 10)
        params["limit"] = params["per_page"]

        try:
            if session_id:
                manager = TurnManager(session_id=session_id)
                payload = manager.run_people_search(params=params, channel=channel, account_id=account_id)
            else:
                payload = LeadSourceRouter().search_people(
                    params=params,
                    preferred_source=channel,
                    session_id=None,
                    account_id=account_id,
                )
        except ConversationSession.DoesNotExist:
            return Response({"error": "session not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("Agent people search failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # ── Persist search_run_id in session state for downstream flow ───────
        _search_run_id = payload.get("search_run_id") or str(payload.get("search_run_id", ""))
        if session_id and _search_run_id:
            try:
                _session = ConversationSession.objects.get(session_id=session_id)
                _state = _session.state or {}
                _state["search_run_id"] = _search_run_id
                _session.state = _state
                _session.save(update_fields=["state", "updated_at"])
            except ConversationSession.DoesNotExist:
                pass

        return Response(payload, status=status.HTTP_200_OK)


class AgentConversationStreamView(APIView):
    """
    SSE streaming endpoint — returns Server-Sent Events so the frontend
    sees text appearing as it's generated instead of waiting for the full response.

    POST /agent/conversation/stream/
    Body: { "session_id": "...", "text": "..." }
    Response: text/event-stream with JSON events
    """

    def post(self, request):
        import json
        from django.http import StreamingHttpResponse

        session_id = request.data.get("session_id")
        user_text = request.data.get("text", "").strip()
        if not session_id or not user_text:
            return Response({"error": "session_id and text required"}, status=status.HTTP_400_BAD_REQUEST)
        if not _is_rollout_enabled_for_session(session_id):
            return Response({"error": "agent runtime not enabled"}, status=status.HTTP_403_FORBIDDEN)

        def event_stream():
            try:
                # Phase 1: Send "thinking" event immediately (~0ms perceived latency)
                yield f"data: {json.dumps({'type': 'status', 'text': 'processing'})}\n\n"

                manager = TurnManager(session_id=session_id)
                for event in manager.run_message_turn_stream(user_text):
                    yield f"data: {json.dumps(event)}\n\n"

                yield "data: [DONE]\n\n"

            except ConversationSession.DoesNotExist:
                yield f"data: {json.dumps({'type': 'error', 'text': 'session not found'})}\n\n"
            except Exception as exc:
                logger.exception("SSE stream failed: %s", exc)
                yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # Disable nginx buffering
        return response


# ─── 1. Lead Selection + Lead List Creation ──────────────────────────────────
# POST /api/agent/v1/leads/select/
# Body: { "session_id", "search_run_id" (optional), "selection_percent": 100|75|50|25, "lead_ids": [] (optional) }

class AgentLeadSelectionView(APIView):
    """
    Select leads from a search run (by % or explicit IDs) and create a lead list
    in lead_lists. Also updates leads.lead_list_id so the send-to-leads fallback works.
    Selected lead IDs are stored in session state for downstream use.
    """

    def post(self, request):
        session_id = request.data.get("session_id")
        search_run_id = request.data.get("search_run_id")
        selection_percent = int(request.data.get("selection_percent", 100))
        explicit_lead_ids = request.data.get("lead_ids")  # optional override

        if not session_id:
            return Response({"error": "session_id required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = LeadSelectionService.select_leads_and_create_list(
                session_id=session_id,
                search_run_id=search_run_id,
                selection_percent=selection_percent,
                explicit_lead_ids=explicit_lead_ids
            )
            result["next_action"] = {"type": "call_api", "endpoint": "/api/agent/v1/campaigns/create/"}
            return Response(result, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Lead selection failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─── 2. Campaign Create ─────────────────────────────────────────────────────
# POST /api/agent/v1/campaigns/create/
# Body: { "session_id", "campaign_name", "creation_mode" (default "ai") }

class AgentCampaignCreateView(APIView):
    """Create a campaign linked to a lead list."""

    def post(self, request):
        session_id = request.data.get("session_id")
        campaign_name = request.data.get("campaign_name", "AI powered")
        creation_mode = request.data.get("creation_mode", "ai")
        lead_list_id = request.data.get("lead_list_id")
        search_run_id = request.data.get("search_run_id")

        if not session_id:
            return Response({"error": "session_id required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = CampaignService.create_campaign(
                session_id=session_id,
                campaign_name=campaign_name,
                creation_mode=creation_mode,
                lead_list_id=lead_list_id,
                search_run_id=search_run_id
            )
            result["next_action"] = {
                "type": "call_api",
                "endpoint": "/api/agent/v1/conversation/message/",
                "hint": "Send campaign details (goal, tone, audience) to start clarification",
            }
            return Response(result, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Campaign create failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─── 3. Campaign Approve ────────────────────────────────────────────────────
# POST /api/agent/v1/campaigns/approve/
# Body: { "session_id", "campaign_id" (optional, from state) }

class AgentCampaignApproveView(APIView):
    """Approve a campaign - sets status to 'approved'."""

    def post(self, request):
        session_id = request.data.get("session_id")
        campaign_id = request.data.get("campaign_id")

        if not session_id:
            return Response({"error": "session_id required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = CampaignService.approve_campaign(
                session_id=session_id,
                campaign_id=campaign_id
            )
            result["next_action"] = {"type": "call_api", "endpoint": "/api/agent/v1/campaigns/sequences/"}
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Campaign approve failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─── 4. Sequence List ───────────────────────────────────────────────────────
# GET  /api/agent/v1/campaigns/sequences/?session_id=X&campaign_id=Y
# POST /api/agent/v1/campaigns/sequences/  (same params in body)

class AgentCampaignSequenceView(APIView):
    """Get sequence list (steps + emails) for a campaign."""

    def _get_sequences(self, session_id, campaign_id, request):
        try:
            result = CampaignService.get_campaign_sequences(
                session_id=session_id,
                campaign_id=campaign_id
            )
            
            # Apply preview mode template replacement for display
            if result.get("success") and result.get("data", {}).get("steps"):
                from api.services.template_replacer import TemplateReplacer
                user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
                
                if user:
                    for step in result["data"]["steps"]:
                        email = step.get("email")
                        if email:
                            replaced = TemplateReplacer.replace_email_content(
                                email.get("subject", ""),
                                email.get("body", ""),
                                user,
                                preview_mode=True
                            )
                            email["subject"] = replaced["subject"]
                            email["body"] = replaced["body"]
            
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Get sequences failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        return self._get_sequences(
            session_id=request.query_params.get("session_id"),
            campaign_id=request.query_params.get("campaign_id"),
            request=request
        )

    def post(self, request):
        return self._get_sequences(
            session_id=request.data.get("session_id"),
            campaign_id=request.data.get("campaign_id"),
            request=request
        )


# ─── Auth Helper ────────────────────────────────────────────────────────────
def _resolve_user(request):
    """Resolve the authenticated user from DRF request.
    
    DRF wraps Django's HttpRequest and may not see the user set by
    JWTAuthenticationMiddleware if DEFAULT_AUTHENTICATION_CLASSES was
    previously empty. This helper checks both DRF and Django layers.
    """
    # DRF layer (works once JWTMiddlewareAuthentication is registered)
    user = getattr(request, 'user', None)
    if user and getattr(user, 'is_authenticated', False):
        return user

    # Fallback: middleware may have set user_id on the Django request
    user_id = getattr(request, 'user_id', None)
    if user_id:
        from authentication.models import User
        try:
            return User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            pass

    return None


# ─── 5. Send Campaign Email ─────────────────────────────────────────────────
# POST /api/agent/v1/campaigns/send-email/
# Body: { "email_id", "recipient_email" }

class AgentCampaignSendEmailView(APIView):
    """Send a campaign email via Gmail OAuth or SMTP fallback."""

    def post(self, request):
        from api.services.gmail_oauth_service import GmailOAuthService
        from api.services.gmail_service import GmailService
        from django.conf import settings
        from api.models import SentEmail

        email_id = request.data.get("email_id")
        recipient_email = request.data.get("recipient_email")

        if not email_id or not recipient_email:
            return Response(
                {"error": "email_id and recipient_email are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Require authentication
            user = _resolve_user(request)
            if not user:
                return Response(
                    {"error": "Authentication required. Please log in to send emails."},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            gmail_service = None
            
            # Priority 1: User's own SMTP App Password config
            try:
                from authentication.models import UserEmailConfig
                cfg = UserEmailConfig.objects.get(user=user)
                gmail_service = GmailService(
                    sender_email=cfg.from_email,
                    app_password=cfg.app_password,
                    smtp_host=cfg.smtp_host,
                    smtp_port=cfg.smtp_port,
                    from_name=cfg.from_name,
                )
                logger.info(f"Using user SMTP config: {cfg.from_email}")
            except UserEmailConfig.DoesNotExist:
                pass
            
            # Priority 2: Gmail OAuth
            if not gmail_service:
                oauth_service = GmailOAuthService(user)
                if oauth_service.is_connected():
                    gmail_service = oauth_service
                    logger.info("Using Gmail OAuth for authenticated user")
            
            # No fallback - user must configure their email
            if not gmail_service:
                return Response(
                    {"error": "Email not configured. Please add your email settings in the Settings menu or connect Gmail OAuth."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            email = CampaignEmail.objects.get(id=email_id)
            step = email.step
            campaign_id = str(step.campaign_id)

            # Look up real lead name and id by recipient email
            from api.models import Lead
            lead_obj = Lead.objects.filter(email=recipient_email).only('id', 'first_name', 'last_name', 'company_name').first()
            real_name = f"{lead_obj.first_name or ''} {lead_obj.last_name or ''}".strip() if lead_obj else ""
            lead_id_str = str(lead_obj.id) if lead_obj else None

            # Personalize subject + body with user and lead data
            from api.services.template_replacer import TemplateReplacer
            lead_data = {
                "first_name": lead_obj.first_name if lead_obj else "",
                "last_name": lead_obj.last_name if lead_obj else "",
                "company_name": lead_obj.company_name if lead_obj else ""
            }
            replaced = TemplateReplacer.replace_email_content(email.subject, email.body, user, lead_data)
            personalized_subject = replaced["subject"]
            personalized_body = replaced["body"]

            result = gmail_service.send_email(
                to_email=recipient_email,
                subject=personalized_subject,
                body=personalized_body,
            )

            if result.get("success"):
                sent_email = SentEmail.objects.create(
                    campaign_id=campaign_id,
                    step_order=step.step_order,
                    recipient_email=recipient_email,
                    recipient_name=real_name,
                    subject=personalized_subject,
                    body=personalized_body,
                    sent_from=result["sender"],
                    status='sent',
                    metadata={
                        "lead_id": lead_id_str,
                        "gmail_message_id": result.get("message_id"),
                    }
                )
                return Response({
                    "success": True,
                    "message": f"Email sent successfully to {recipient_email}",
                    "email_id": str(email_id),
                    "recipient": recipient_email,
                    "sent_email_id": str(sent_email.id),
                    "sent_from": result["sender"],
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "success": False,
                    "error": result.get("error", "Failed to send email")
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except CampaignEmail.DoesNotExist:
            return Response(
                {"error": f"Email with ID {email_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as exc:
            logger.exception("Send email failed: %s", exc)
            return Response(
                {"error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ─── 5b. Update Campaign Email Content ──────────────────────────────────────
# POST /api/agent/v1/emails/update/
# Body: { "email_id", "subject", "body" }

class AgentEmailUpdateView(APIView):
    """Update subject and/or body of a campaign email before sending."""

    def post(self, request):
        email_id = request.data.get("email_id")
        new_subject = request.data.get("subject")
        new_body = request.data.get("body")

        if not email_id:
            return Response({"error": "email_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = _resolve_user(request)
            if not user:
                return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

            email = CampaignEmail.objects.get(id=email_id)

            if new_subject is not None:
                email.subject = new_subject
            if new_body is not None:
                email.body = new_body
            email.save(update_fields=["subject", "body"])

            return Response({"success": True, "email_id": str(email_id)}, status=status.HTTP_200_OK)

        except CampaignEmail.DoesNotExist:
            return Response({"error": f"Email {email_id} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("Email update failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─── 5c. List User Campaigns ─────────────────────────────────────────────────
# GET /api/agent/v1/campaigns/list/

class AgentCampaignListView(APIView):
    """Return all campaigns created by the authenticated user with detailed stats."""

    def get(self, request):
        from api.models import SentEmail, CampaignStep
        from django.db.models import Count, Q
        
        user = _resolve_user(request)
        if not user:
            return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        # Resolve user's org so we can also surface campaigns whose created_by
        # was never set (e.g. created via campaign_agent before this fix).
        user_org_id = getattr(user, 'account_id', None)
        if user_org_id:
            user_org_id = str(user_org_id)

        if user_org_id:
            campaigns = Campaign.objects.filter(
                Q(created_by=user.id) | Q(org_id=user_org_id)
            ).order_by("-created_at")
        else:
            campaigns = Campaign.objects.filter(created_by=user.id).order_by("-created_at")
        
        data = []
        for c in campaigns:
            # Get campaign steps
            steps = CampaignStep.objects.filter(campaign_id=c.id).order_by('step_order')
            total_steps = steps.count()
            
            # Get email statistics
            campaign_id_str = str(c.id)
            campaign_id_no_dash = campaign_id_str.replace('-', '')
            
            sent_emails = SentEmail.objects.filter(
                Q(campaign_id=campaign_id_str) | Q(campaign_id=campaign_id_no_dash)
            )
            
            total_sent = sent_emails.count()
            emails_by_status = sent_emails.values('status').annotate(count=Count('status'))
            
            status_counts = {item['status']: item['count'] for item in emails_by_status}
            
            # Get lead list info
            lead_count = 0
            if c.lead_list_id:
                try:
                    from api.models import Lead
                    lead_count = Lead.objects.filter(lead_list_id=c.lead_list_id).count()
                except:
                    pass
            # Fallback: count leads enrolled via CampaignLeadStatus (e.g. test runs)
            if not lead_count:
                try:
                    from api.models import CampaignLeadStatus
                    lead_count = CampaignLeadStatus.objects.filter(campaign_id=c.id).count()
                except:
                    pass
            
            # Calculate remaining emails
            total_to_send = lead_count * total_steps if lead_count and total_steps else 0
            remaining = max(0, total_to_send - total_sent)
            
            # Get step schedule info
            step_info = []
            for step in steps:
                step_emails = sent_emails.filter(step_order=step.step_order).count()
                step_info.append({
                    'step_order': step.step_order,
                    'delay_days': step.delay_days,
                    'emails_sent': step_emails,
                    'emails_remaining': max(0, lead_count - step_emails) if lead_count else 0
                })
            
            data.append({
                "id": str(c.id),
                "name": c.name,
                "status": c.status,
                "created_at": c.created_at.isoformat(),
                "stats": {
                    "total_leads": lead_count,
                    "total_steps": total_steps,
                    "total_sent": total_sent,
                    "total_to_send": total_to_send,
                    "remaining": remaining,
                    "sent": status_counts.get('sent', 0),
                    "delivered": status_counts.get('delivered', 0),
                    "opened": status_counts.get('opened', 0),
                    "replied": status_counts.get('replied', 0),
                    "bounced": status_counts.get('bounced', 0),
                    "failed": status_counts.get('failed', 0),
                },
                "steps": step_info
            })
        
        return Response({"success": True, "campaigns": data}, status=status.HTTP_200_OK)


# ─── 5d. Stop or Delete a Campaign ───────────────────────────────────────────
# POST /api/agent/v1/campaigns/manage/
# Body: { "campaign_id", "action": "stop" | "delete" }

class AgentCampaignManageView(APIView):
    """Stop, delete, or get progress for a campaign."""

    def post(self, request):
        user = _resolve_user(request)
        if not user:
            return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        campaign_id = request.data.get("campaign_id")
        action = request.data.get("action")

        if not campaign_id or action not in ("stop", "delete", "progress"):
            return Response(
                {"error": "campaign_id and action ('stop', 'delete', or 'progress') are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.db.models import Q

        user_org_id = getattr(user, 'account_id', None)
        if user_org_id:
            user_org_id = str(user_org_id)

        try:
            ownership_q = Q(created_by=user.id)
            if user_org_id:
                ownership_q |= Q(org_id=user_org_id)
            campaign = Campaign.objects.get(Q(id=campaign_id) & ownership_q)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=status.HTTP_404_NOT_FOUND)

        if action == "stop":
            campaign.status = "blocked"
            campaign.save(update_fields=["status", "updated_at"])
            return Response({"success": True, "message": "Campaign stopped.", "campaign_id": str(campaign_id)})

        if action == "delete":
            campaign.delete()
            return Response({"success": True, "message": "Campaign deleted.", "campaign_id": str(campaign_id)})

        if action == "progress":
            from api.models import SentEmail, CampaignLeadStatus, CampaignStep as CampaignStepModel
            from django.db.models import Count, Q as DQ

            cid = str(campaign.id)
            cid_no_dash = cid.replace('-', '')

            # ── Steps info ──────────────────────────────────────────────────
            steps = CampaignStepModel.objects.filter(campaign=campaign).order_by("step_order")
            total_steps = steps.count()

            # ── Sent emails (works for both campaign types) ─────────────────
            sent_qs = SentEmail.objects.filter(
                DQ(campaign_id=cid) | DQ(campaign_id=cid_no_dash)
            )
            total_sent = sent_qs.count()
            status_counts = {
                row["status"]: row["count"]
                for row in sent_qs.values("status").annotate(count=Count("status"))
            }

            # ── Per-lead sequence tracking (CampaignLeadStatus) ─────────────
            lead_statuses = CampaignLeadStatus.objects.filter(campaign=campaign)
            total_leads_enrolled = lead_statuses.count()
            lead_status_breakdown = {
                row["status"]: row["count"]
                for row in lead_statuses.values("status").annotate(count=Count("status"))
            }

            # ── Determine campaign type ─────────────────────────────────────
            # Test campaigns: enrolled via test_mode (Lead.primary_source='test')
            # or exactly 1 lead enrolled with no lead_list on campaign
            is_test = (
                total_leads_enrolled == 1
                and not campaign.lead_list_id
            )
            campaign_type = "test" if is_test else "lead_list"

            # ── Fallback lead count from lead_list for bulk campaigns ───────
            lead_list_count = 0
            if campaign.lead_list_id and not is_test:
                try:
                    from api.models import Lead
                    lead_list_count = Lead.objects.filter(
                        lead_list_id=campaign.lead_list_id
                    ).count()
                except Exception:
                    pass

            total_leads = total_leads_enrolled or lead_list_count
            total_to_send = total_leads * total_steps if total_leads and total_steps else 0
            remaining = max(0, total_to_send - total_sent)

            # ── Per-step breakdown ──────────────────────────────────────────
            step_progress = []
            for s in steps:
                step_sent = sent_qs.filter(step_order=s.step_order).count()
                step_progress.append({
                    "step_order": s.step_order,
                    "delay_days": s.delay_days,
                    "condition": s.condition,
                    "emails_sent": step_sent,
                    "emails_remaining": max(0, total_leads - step_sent) if total_leads else 0,
                })

            # ── Compute overall progress percentage ─────────────────────────
            progress_pct = round((total_sent / total_to_send) * 100, 1) if total_to_send else (100.0 if total_sent else 0.0)

            return Response({
                "success": True,
                "campaign_id": cid,
                "campaign_name": campaign.name,
                "campaign_type": campaign_type,
                "campaign_status": campaign.status,
                "created_at": campaign.created_at.isoformat(),
                "progress": {
                    "percent_complete": progress_pct,
                    "total_leads": total_leads,
                    "total_steps": total_steps,
                    "total_to_send": total_to_send,
                    "total_sent": total_sent,
                    "remaining": remaining,
                    "email_status": {
                        "sent": status_counts.get("sent", 0),
                        "delivered": status_counts.get("delivered", 0),
                        "opened": status_counts.get("opened", 0),
                        "clicked": status_counts.get("clicked", 0),
                        "replied": status_counts.get("replied", 0),
                        "bounced": status_counts.get("bounced", 0),
                        "failed": status_counts.get("failed", 0),
                    },
                    "lead_status": {
                        "pending": lead_status_breakdown.get("pending", 0),
                        "in_sequence": lead_status_breakdown.get("in_sequence", 0),
                        "completed": lead_status_breakdown.get("completed", 0),
                        "replied": lead_status_breakdown.get("replied", 0),
                        "bounced": lead_status_breakdown.get("bounced", 0),
                        "unsubscribed": lead_status_breakdown.get("unsubscribed", 0),
                    },
                },
                "steps": step_progress,
            })


# ─── 6. Send Campaign to Leads ──────────────────────────────────────────────
# POST /api/agent/v1/campaigns/send-to-leads/
# Body: { "campaign_id", "step_order" (optional, default 1), "test_mode": true/false, "test_email" (required when test_mode) }

class AgentCampaignSendToLeadsView(APIView):
    """Send campaign emails to all leads via Gmail OAuth or SMTP fallback."""

    def post(self, request):
        from api.services.gmail_oauth_service import GmailOAuthService
        from api.services.gmail_service import GmailService
        from django.conf import settings

        campaign_id = request.data.get("campaign_id")
        step_order = request.data.get("step_order", 1)
        test_mode = request.data.get("test_mode", False)
        test_email = request.data.get("test_email")
        session_id = request.data.get("session_id")
        selection_percent = int(request.data.get("selection_percent", 100))

        if not campaign_id:
            return Response(
                {"error": "campaign_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Require authentication
            user = _resolve_user(request)
            if not user:
                return Response(
                    {"error": "Authentication required. Please log in to send emails."},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            gmail_service = None

            # Priority 1: User's own SMTP App Password config
            try:
                from authentication.models import UserEmailConfig
                cfg = UserEmailConfig.objects.get(user=user)
                gmail_service = GmailService(
                    sender_email=cfg.from_email,
                    app_password=cfg.app_password,
                    smtp_host=cfg.smtp_host,
                    smtp_port=cfg.smtp_port,
                    from_name=cfg.from_name,
                )
                logger.info(f"Using user SMTP config: {cfg.from_email}")
            except UserEmailConfig.DoesNotExist:
                pass

            # Priority 2: Gmail OAuth
            if not gmail_service:
                oauth_service = GmailOAuthService(user)
                if oauth_service.is_connected():
                    gmail_service = oauth_service
                    logger.info("Using Gmail OAuth for authenticated user")

            # No fallback - user must configure their email
            if not gmail_service:
                return Response(
                    {"error": "Email not configured. Please add your email settings in the Settings menu or connect Gmail OAuth."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Normalize campaign_id
            campaign_id_normalized = campaign_id.replace('-', '')
            
            # Get campaign and email
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, lead_list_id FROM campaigns WHERE id = %s",
                    [campaign_id_normalized]
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Campaign {campaign_id} not found")
                
                campaign_id_db = row[0]
                campaign_name = row[1]
                lead_list_id = row[2]
            
            # Get the email for this step
            try:
                step = CampaignStep.objects.get(
                    campaign_id=campaign_id_db,
                    step_order=step_order
                )
                email = step.email
            except CampaignStep.DoesNotExist:
                return Response(
                    {"error": f"Step {step_order} not found for campaign"},
                    status=status.HTTP_404_NOT_FOUND
                )
            except CampaignEmail.DoesNotExist:
                return Response(
                    {"error": f"Email not found for step {step_order}"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Test mode: enroll a single recipient and send Step 1 immediately.
            # Follow-up steps are handled by the scheduler (send_campaign_sequences).
            if test_mode:
                if not test_email:
                    return Response(
                        {"error": "test_email is required when test_mode is true"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                from api.models import Lead, CampaignLeadStatus, SentEmail as SentEmailModel, Campaign as CampaignModel
                from api.services.template_replacer import TemplateReplacer
                from django.utils import timezone as tz

                recipient_name = request.data.get("recipient_name", "").strip()
                name_parts = recipient_name.split(" ", 1) if recipient_name else []
                first_name = name_parts[0] if name_parts else "there"
                last_name = name_parts[1] if len(name_parts) > 1 else ""

                # Get or create a Lead so the scheduler can send follow-up steps
                lead, created = Lead.objects.get_or_create(
                    email=test_email,
                    defaults={"first_name": first_name, "last_name": last_name, "primary_source": "test", "channel": "test"}
                )
                if not created and recipient_name:
                    lead.first_name = first_name
                    lead.last_name = last_name
                    lead.save(update_fields=["first_name", "last_name"])

                lead_data = {
                    "first_name": lead.first_name or first_name,
                    "last_name": lead.last_name or last_name,
                    "company_name": lead.company_name or "",
                }
                replaced = TemplateReplacer.replace_email_content(email.subject, email.body, user, lead_data)

                result = gmail_service.send_email(
                    to_email=test_email,
                    subject=replaced['subject'],
                    body=replaced['body']
                )

                if not result.get("success"):
                    return Response({"success": False, "error": result.get("error")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                sender_address = result.get("sender", "")
                total_steps = CampaignStep.objects.filter(campaign_id=campaign_id_db).count()

                # Record the sent email
                sent_record = SentEmailModel.objects.create(
                    campaign_id=campaign_id_db,
                    step_order=step_order,
                    recipient_email=test_email,
                    recipient_name=f"{first_name} {last_name}".strip(),
                    subject=replaced['subject'],
                    body=replaced['body'],
                    sent_from=sender_address,
                    status='sent',
                )

                # Enroll lead in campaign sequence so scheduler picks up steps 2+
                new_status = 'completed' if step_order >= total_steps else 'in_sequence'
                CampaignLeadStatus.objects.update_or_create(
                    campaign_id=campaign_id_db,
                    lead=lead,
                    defaults={
                        'last_step_sent': step_order,
                        'last_sent_at': tz.now(),
                        'last_sent_email': sent_record,
                        'status': new_status,
                    }
                )

                # Activate campaign so the scheduler processes follow-up steps
                campaign_obj = CampaignModel.objects.filter(id=campaign_id_db).first()
                if campaign_obj and campaign_obj.status not in ('active', 'completed', 'blocked'):
                    campaign_obj.status = 'active'
                    campaign_obj.save(update_fields=['status', 'updated_at'])

                return Response({
                    "success": True,
                    "test_mode": True,
                    "message": f"Step 1 sent to {test_email}. Follow-up steps will be sent automatically after their configured delays.",
                    "sent_count": 1,
                    "sent_from": sender_address,
                }, status=status.HTTP_200_OK)
            
            # Production mode: send to all leads
            # ── Resolve leads via LeadSelectionService (agent flow) ──────────
            from api.models import ConversationSession as APIConversationSession
            from agent_runtime.services.lead_selection_service import LeadSelectionService

            leads = []
            search_run_id = None

            try:
                campaign_id_with_dashes = '-'.join([
                    campaign_id_db[0:8], campaign_id_db[8:12],
                    campaign_id_db[12:16], campaign_id_db[16:20],
                    campaign_id_db[20:32]
                ]) if len(campaign_id_db) == 32 else campaign_id_db

                # Resolve session: by explicit session_id first, then by campaign_id in state
                session = None
                if session_id:
                    session = APIConversationSession.objects.filter(session_id=session_id).first()
                if not session:
                    session = APIConversationSession.objects.filter(state__campaign_id=campaign_id_db).first()
                if not session:
                    session = APIConversationSession.objects.filter(state__campaign_id=campaign_id_with_dashes).first()

                if session and session.state:
                    state = session.state
                    search_run_id = state.get("search_run_id")
                    selected_lead_ids = state.get("selected_lead_ids")

                    if search_run_id:
                        # If leads not yet selected, run LeadSelectionService now to register
                        # the batch into lead_lists_new and persist selected_lead_ids in session
                        if not selected_lead_ids:
                            selection_result = LeadSelectionService.select_leads_and_create_list(
                                session_id=session.session_id,
                                search_run_id=search_run_id,
                                selection_percent=selection_percent,
                            )
                            session.refresh_from_db()
                            selected_lead_ids = session.state.get("selected_lead_ids", [])
                            logger.info(
                                f"Lead selection registered: {selection_result['selected_count']} leads, "
                                f"lead_list_id={selection_result['lead_list_id']}"
                            )

                        # Query exact leads by their IDs from the selection
                        if selected_lead_ids:
                            placeholders = ','.join(['%s'] * len(selected_lead_ids))
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    f"SELECT l.id, l.email, l.first_name, l.last_name, l.company_name "
                                    f"FROM leads l "
                                    f"WHERE l.id IN ({placeholders}) AND l.email IS NOT NULL",
                                    selected_lead_ids
                                )
                                leads = cursor.fetchall()
                            logger.info(f"Found {len(leads)} leads via lead selection (search_run_id: {search_run_id})")

            except Exception as e:
                logger.warning(f"Could not get leads from session/selection: {e}")

            # Fall back to lead_list_id (campaign column) if selection flow yielded nothing
            if not leads and lead_list_id:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT l.id, l.email, l.first_name, l.last_name, l.company_name
                           FROM leads l
                           WHERE l.lead_list_id = %s AND l.email IS NOT NULL""",
                        [lead_list_id]
                    )
                    leads = cursor.fetchall()
                    logger.info(f"Found {len(leads)} leads from lead_list_id: {lead_list_id}")
            
            if not leads:
                error_msg = "No leads found for this campaign. "
                if search_run_id:
                    error_msg += f"Checked search_run_id: {search_run_id}. "
                if lead_list_id:
                    error_msg += f"Checked lead_list_id: {lead_list_id}. "
                error_msg += "Make sure leads are linked to the campaign via search results or lead list."
                
                return Response(
                    {"error": error_msg},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Send emails to all leads
            sent_count = 0
            failed_count = 0
            failed_emails = []
            sender_address = ""

            from api.models import SentEmail, CampaignLeadStatus, Lead as LeadModel, Campaign as CampaignModel
            from api.services.template_replacer import TemplateReplacer
            from django.utils import timezone as tz

            total_steps = CampaignStep.objects.filter(campaign_id=campaign_id_db).count()

            for lead_id_raw, lead_email, first_name, last_name, company_name in leads:
                # Personalize subject + body with user and lead data
                lead_obj = {
                    "first_name": first_name or "there", 
                    "last_name": last_name or "",
                    "company_name": company_name or ""
                }
                replaced = TemplateReplacer.replace_email_content(email.subject, email.body, user, lead_obj)
                personalized_subject = replaced["subject"]
                personalized_body = replaced["body"]

                result = gmail_service.send_email(
                    to_email=lead_email,
                    subject=personalized_subject,
                    body=personalized_body
                )

                if result.get("success"):
                    sent_count += 1
                    if not sender_address:
                        sender_address = result.get("sender", "")
                    sent_record = SentEmail.objects.create(
                        campaign_id=campaign_id_db,
                        step_order=step_order,
                        recipient_email=lead_email,
                        recipient_name=f"{first_name or ''} {last_name or ''}".strip(),
                        subject=personalized_subject,
                        body=personalized_body,
                        sent_from=sender_address,
                        status='sent',
                        metadata={
                            "lead_id": str(lead_id_raw),
                            "gmail_message_id": result.get("message_id"),
                        }
                    )
                    # Enroll lead in campaign sequence (mirrors test_mode logic)
                    try:
                        lead_obj_db = LeadModel.objects.get(id=lead_id_raw)
                        new_status = 'completed' if step_order >= total_steps else 'in_sequence'
                        CampaignLeadStatus.objects.update_or_create(
                            campaign_id=campaign_id_db,
                            lead=lead_obj_db,
                            defaults={
                                'last_step_sent': step_order,
                                'last_sent_at': tz.now(),
                                'last_sent_email': sent_record,
                                'status': new_status,
                            }
                        )
                    except LeadModel.DoesNotExist:
                        logger.warning(f"Lead {lead_id_raw} not found for CampaignLeadStatus")
                else:
                    failed_count += 1
                    failed_emails.append({
                        "email": lead_email,
                        "error": result.get("error")
                    })
            
            # Activate campaign so the scheduler processes follow-up steps
            if sent_count > 0:
                campaign_obj = CampaignModel.objects.filter(id=campaign_id_db).first()
                if campaign_obj and campaign_obj.status not in ('active', 'completed', 'blocked'):
                    campaign_obj.status = 'active'
                    campaign_obj.save(update_fields=['status', 'updated_at'])

            return Response({
                "success": True,
                "campaign_id": campaign_id_db,
                "campaign_name": campaign_name,
                "step_order": step_order,
                "total_leads": len(leads),
                "sent_count": sent_count,
                "failed_count": failed_count,
                "sent_from": sender_address,
                "failed_emails": failed_emails[:10]
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Send to leads failed: %s", exc)
            return Response(
                {"error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ─── 7. Get Inbox (Sent Emails + Replies) ──────────────────────────────────
# GET /api/agent/v1/inbox/?campaign_id=X&limit=50

class AgentInboxView(APIView):
    """
    Get sent emails and replies for inbox view.
    Pulls from TWO sources:
      1. ``sent_emails``  — emails sent via the agent "Send to All Leads" flow.
      2. ``email_messages`` + ``email_conversation`` — historical campaign emails
         sent via GHL / old pipeline.
    Results are merged, de-duplicated by recipient+subject, and sorted by date.
    """

    def get(self, request):
        from api.models import SentEmail, EmailReply
        from django.db.models import Prefetch, Count, Exists, OuterRef, Q

        campaign_id = request.query_params.get("campaign_id")
        status_filter = request.query_params.get("status")

        # ── Pagination params ─────────────────────────────────────────────
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(int(request.query_params.get("page_size", 10)), 50)

        # Resolve user and their email addresses for filtering
        user = _resolve_user(request)
        user_emails = self._get_user_email_addresses(user)
        org_id = self._resolve_org(request)

        # Debug logging
        logger.info(f"Inbox request - User: {user.email if user else 'None'}, User emails: {user_emails}, Org: {org_id}")

        try:
            inbox_data = []
            seen_keys = set()  # dedup by (recipient_email, subject)

            # ── Source 1: sent_emails (agent flow) ────────────────────────────
            # Prefetch replies in ONE query instead of N+1
            replies_prefetch = Prefetch(
                "replies",
                queryset=EmailReply.objects.order_by("received_at"),
                to_attr="prefetched_replies",
            )
            query = (
                SentEmail.objects
                .prefetch_related(replies_prefetch)
                .annotate(
                    _reply_count=Count("replies"),
                    _has_unread=Exists(
                        EmailReply.objects.filter(
                            sent_email=OuterRef("pk"), is_read=False
                        )
                    ),
                )
                .order_by("-sent_at")
            )

            # Filter by user's email addresses (primary filter)
            if user_emails:
                query = query.filter(sent_from__in=user_emails)
                logger.info(f"Filtering by user emails: {user_emails}")
            else:
                # User has no email configuration - return empty queryset
                logger.warning(f"No user emails found for filtering! User: {user}")
                query = query.none()  # Return empty queryset

            if campaign_id:
                cid_no_dash = campaign_id.replace("-", "")
                query = query.filter(campaign_id__in=[campaign_id, cid_no_dash])

            if status_filter and status_filter != "all":
                query = query.filter(status=status_filter)

            # Total count BEFORE slicing (for pagination metadata)
            total_agent = query.count()

            # Slice for the requested page
            offset = (page - 1) * page_size
            page_qs = query[offset : offset + page_size]

            for se in page_qs:
                replies_list = [
                    {
                        "id": str(r.id),
                        "from_email": r.from_email,
                        "from_name": r.from_name,
                        "subject": r.subject,
                        "body": r.body,
                        "body_preview": r.body[:100] + "..." if len(r.body) > 100 else r.body,
                        "received_at": r.received_at.isoformat(),
                        "sentiment": r.sentiment,
                        "is_read": r.is_read,
                    }
                    for r in se.prefetched_replies
                ]
                key = (se.recipient_email, (se.subject or "")[:60])
                seen_keys.add(key)

                inbox_data.append({
                    "id": str(se.id),
                    "campaign_id": se.campaign_id,
                    "step_order": se.step_order,
                    "recipient_email": se.recipient_email,
                    "recipient_name": se.recipient_name or "",
                    "subject": se.subject,
                    "body": se.body,
                    "body_preview": se.body[:200] + "..." if len(se.body) > 200 else se.body,
                    "sent_at": se.sent_at.isoformat(),
                    "sent_from": se.sent_from,
                    "status": se.status,
                    "opened_at": se.opened_at.isoformat() if se.opened_at else None,
                    "replied_at": se.replied_at.isoformat() if se.replied_at else None,
                    "reply_count": se._reply_count,
                    "has_unread_replies": se._has_unread,
                    "replies": replies_list,
                    "latest_reply": replies_list[-1] if replies_list else None,
                    "source": "agent",
                })

            # ── Source 2: historical (only on last page / if agent emails didn't fill page)
            remaining = page_size - len(inbox_data)
            total_combined = total_agent
            if remaining > 0 and offset + page_size >= total_agent:
                historical_offset = max(0, offset - total_agent)
                historical = self._fetch_historical_emails(
                    org_id=org_id,
                    campaign_id=campaign_id,
                    limit=remaining,
                    seen_keys=seen_keys,
                    offset=historical_offset,
                    user_emails=user_emails,
                )
                inbox_data.extend(historical)
                # Rough total (historical count is expensive, estimate)
                total_combined += len(historical)

            total_pages = math.ceil(total_combined / page_size) if total_combined else 1

            return Response(
                {
                    "success": True,
                    "emails": inbox_data,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total_combined,
                        "total_pages": total_pages,
                        "has_next": page < total_pages,
                        "has_prev": page > 1,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as exc:
            logger.exception("Get inbox failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _get_user_email_addresses(user):
        """Get all email addresses associated with the user for filtering sent emails."""
        if not user:
            logger.warning("No user provided to _get_user_email_addresses")
            return []
        
        email_addresses = []
        
        # Get Gmail OAuth email
        try:
            from authentication.models import UserGmailToken
            gmail_token = UserGmailToken.objects.filter(user=user).first()
            if gmail_token and gmail_token.gmail_address:
                email_addresses.append(gmail_token.gmail_address)
                logger.info(f"Found Gmail OAuth email: {gmail_token.gmail_address}")
        except Exception as e:
            logger.warning(f"Error getting Gmail token: {e}")
        
        # Get SMTP config email
        try:
            from authentication.models import UserEmailConfig
            email_config = UserEmailConfig.objects.filter(user=user).first()
            if email_config and email_config.from_email:
                email_addresses.append(email_config.from_email)
                logger.info(f"Found SMTP email: {email_config.from_email}")
        except Exception as e:
            logger.warning(f"Error getting email config: {e}")
        
        unique_emails = list(set(email_addresses))  # Remove duplicates
        logger.info(f"User {user.email} has email addresses: {unique_emails}")
        return unique_emails

    @staticmethod
    def _resolve_org(request):
        """Best-effort org_id from the authenticated user."""
        user = _resolve_user(request)
        if user:
            account_id = getattr(user, "account_id", None)
            if account_id:
                return str(account_id)
            # Check account_users table
            try:
                from authentication.models import AccountUser
                au = AccountUser.objects.filter(user=user).first()
                if au:
                    return str(au.account_id)
            except Exception:
                pass
        return None

    @staticmethod
    def _fetch_historical_emails(org_id, campaign_id, limit, seen_keys, offset=0, user_emails=None):
        """
        Pull historical outbound emails from ``email_messages`` joined with
        ``email_conversation`` so we can display old campaign sends.
        Filter by user_emails if provided to show only emails sent by this user.
        Note: email_messages table may not have sent_from field, so we filter by campaign ownership.
        """
        results = []
        try:
            where_clauses = ["em.direction = 'outbound' OR em.sender_type = 'agent'"]
            params = []

            if campaign_id:
                cid = campaign_id.replace("-", "")
                where_clauses.append(
                    "(ec.campaign_instance_id = %s OR ec.campaign_instance_id = %s)"
                )
                params += [campaign_id, cid]

            # For historical emails, we can't filter by sent_from directly
            # Instead, we rely on org_id scoping which is already in place
            if org_id:
                # Scope via campaign_instances(_new).org_id
                where_clauses.append(
                    """ec.campaign_instance_id IN (
                        SELECT id FROM campaign_instances WHERE org_id = %s
                        UNION
                        SELECT id FROM campaign_instances_new WHERE org_id = %s
                    )"""
                )
                params += [org_id, org_id]

            where_sql = " AND ".join(where_clauses)

            sql = f"""
                SELECT
                    em.id,
                    ec.campaign_instance_id,
                    em.message,
                    em.created_at,
                    em.status,
                    l.email       AS recipient_email,
                    l.first_name  AS first_name,
                    l.last_name   AS last_name
                FROM email_messages em
                JOIN email_conversation ec ON ec.id = em.conversation_id
                LEFT JOIN agent_leads l    ON l.id  = ec.lead_id
                WHERE {where_sql}
                ORDER BY em.created_at DESC
                LIMIT %s OFFSET %s
            """
            params.append(limit * 2)  # over-fetch to handle dedup
            params.append(offset)

            with connection.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

            for row in rows:
                msg_id, ci_id, body, created_at, msg_status, recip_email, fname, lname = row
                recip_email = recip_email or "unknown"
                subject = _extract_subject(body)
                key = (recip_email, subject[:60])
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                full_name = " ".join(filter(None, [fname, lname])) or recip_email

                # Fetch inbound replies for this conversation
                replies_list = AgentInboxView._fetch_historical_replies(msg_id)

                results.append({
                    "id": str(msg_id),
                    "campaign_id": str(ci_id) if ci_id else "",
                    "step_order": 1,
                    "recipient_email": recip_email,
                    "recipient_name": full_name,
                    "subject": subject,
                    "body": body or "",
                    "body_preview": (body or "")[:200] + "..." if body and len(body) > 200 else (body or ""),
                    "sent_at": created_at.isoformat() if created_at else "",
                    "sent_from": "",
                    "status": msg_status or "sent",
                    "opened_at": None,
                    "replied_at": replies_list[-1]["received_at"] if replies_list else None,
                    "reply_count": len(replies_list),
                    "has_unread_replies": any(not r.get("is_read", True) for r in replies_list),
                    "replies": replies_list,
                    "latest_reply": replies_list[-1] if replies_list else None,
                    "source": "historical",
                })
                if len(results) >= limit:
                    break

        except Exception as exc:
            logger.warning("Historical email fetch failed (non-fatal): %s", exc)

        return results

    @staticmethod
    def _fetch_historical_replies(outbound_msg_id):
        """Get inbound replies from the same conversation as the outbound msg."""
        replies = []
        try:
            sql = """
                SELECT em2.id, em2.message, em2.created_at, em2.is_read,
                       l.email, l.first_name, l.last_name
                FROM email_messages em2
                JOIN email_messages em_orig ON em_orig.conversation_id = em2.conversation_id
                LEFT JOIN email_conversation ec ON ec.id = em2.conversation_id
                LEFT JOIN agent_leads l ON l.id = ec.lead_id
                WHERE em_orig.id = %s
                  AND (em2.direction = 'inbound' OR em2.sender_type = 'lead')
                  AND em2.id != %s
                ORDER BY em2.created_at ASC
            """
            with connection.cursor() as cur:
                cur.execute(sql, [outbound_msg_id, outbound_msg_id])
                for r in cur.fetchall():
                    r_id, body, created_at, is_read, email, fname, lname = r
                    replies.append({
                        "id": str(r_id),
                        "from_email": email or "unknown",
                        "from_name": " ".join(filter(None, [fname, lname])) or email or "",
                        "subject": _extract_subject(body),
                        "body": body or "",
                        "body_preview": (body or "")[:100] + "..." if body and len(body) > 100 else (body or ""),
                        "received_at": created_at.isoformat() if created_at else "",
                        "sentiment": None,
                        "is_read": bool(is_read),
                    })
        except Exception as exc:
            logger.warning("Historical reply fetch failed (non-fatal): %s", exc)
        return replies


def _extract_subject(body: str) -> str:
    """Pull a short subject line from an email body."""
    if not body:
        return "(no subject)"
    # First line or first 80 chars
    first_line = body.strip().split("\n")[0].strip()
    if len(first_line) > 80:
        first_line = first_line[:77] + "..."
    return first_line or "(no subject)"


# ─── 8. Get Email Thread (Sent Email + All Replies) ────────────────────────
# GET /api/agent/v1/inbox/thread/<sent_email_id>/

class AgentEmailThreadView(APIView):
    """Get full email thread (sent email + all replies).
    Works for both agent-flow emails (sent_emails table) and
    historical emails (email_messages table).
    """

    def get(self, request, sent_email_id):
        from api.models import SentEmail, EmailReply

        # ── Try agent flow table first ────────────────────────────────────
        try:
            sent_email = SentEmail.objects.get(id=sent_email_id)
            replies = sent_email.replies.all().order_by("received_at")

            thread_data = {
                "sent_email": {
                    "id": str(sent_email.id),
                    "campaign_id": sent_email.campaign_id,
                    "step_order": sent_email.step_order,
                    "recipient_email": sent_email.recipient_email,
                    "recipient_name": sent_email.recipient_name,
                    "subject": sent_email.subject,
                    "body": sent_email.body,
                    "sent_at": sent_email.sent_at.isoformat(),
                    "sent_from": sent_email.sent_from,
                    "status": sent_email.status,
                },
                "replies": [
                    {
                        "id": str(reply.id),
                        "from_email": reply.from_email,
                        "from_name": reply.from_name,
                        "subject": reply.subject,
                        "body": reply.body,
                        "received_at": reply.received_at.isoformat(),
                        "is_read": reply.is_read,
                        "sentiment": reply.sentiment,
                    }
                    for reply in replies
                ],
            }

            # Mark replies as read
            replies.filter(is_read=False).update(is_read=True)

            return Response({"success": True, "thread": thread_data}, status=status.HTTP_200_OK)

        except SentEmail.DoesNotExist:
            pass  # Fall through to historical lookup

        # ── Try historical email_messages table ───────────────────────────
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """SELECT em.id, em.message, em.created_at, em.status,
                              ec.campaign_instance_id,
                              l.email, l.first_name, l.last_name
                       FROM email_messages em
                       JOIN email_conversation ec ON ec.id = em.conversation_id
                       LEFT JOIN agent_leads l ON l.id = ec.lead_id
                       WHERE em.id = %s""",
                    [sent_email_id],
                )
                row = cur.fetchone()

            if not row:
                return Response({"error": "Email thread not found"}, status=status.HTTP_404_NOT_FOUND)

            msg_id, body, created_at, msg_status, ci_id, recip_email, fname, lname = row
            full_name = " ".join(filter(None, [fname, lname])) or recip_email or ""

            # Get replies from same conversation
            historical_replies = AgentInboxView._fetch_historical_replies(msg_id)

            # Mark historical replies as read
            try:
                with connection.cursor() as cur:
                    cur.execute(
                        """UPDATE email_messages SET is_read = 1
                           WHERE conversation_id = (
                               SELECT conversation_id FROM email_messages WHERE id = %s
                           ) AND (direction = 'inbound' OR sender_type = 'lead')""",
                        [sent_email_id],
                    )
            except Exception:
                pass

            thread_data = {
                "sent_email": {
                    "id": str(msg_id),
                    "campaign_id": str(ci_id) if ci_id else "",
                    "step_order": 1,
                    "recipient_email": recip_email or "",
                    "recipient_name": full_name,
                    "subject": _extract_subject(body),
                    "body": body or "",
                    "sent_at": created_at.isoformat() if created_at else "",
                    "sent_from": "",
                    "status": msg_status or "sent",
                },
                "replies": historical_replies,
            }

            return Response({"success": True, "thread": thread_data}, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.exception("Get email thread failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─── 9. Add Reply (Manual/Simulated) ───────────────────────────────────────
# POST /api/agent/v1/inbox/reply/
# Body: { "sent_email_id", "from_email", "from_name", "subject", "body", "sentiment" }

class AgentAddReplyView(APIView):
    """Add a reply to a sent email (for testing/simulation)."""

    def post(self, request):
        from api.models import SentEmail, EmailReply

        sent_email_id = request.data.get("sent_email_id")
        from_email = request.data.get("from_email")
        from_name = request.data.get("from_name", "")
        subject = request.data.get("subject", "Re: ")
        body = request.data.get("body")
        sentiment = request.data.get("sentiment", "neutral")

        if not sent_email_id or not from_email or not body:
            return Response(
                {"error": "sent_email_id, from_email, and body are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sent_email = SentEmail.objects.get(id=sent_email_id)

            reply = EmailReply.objects.create(
                sent_email=sent_email,
                from_email=from_email,
                from_name=from_name,
                subject=subject,
                body=body,
                sentiment=sentiment,
                is_read=False,
            )

            sent_email.status = "replied"
            sent_email.replied_at = reply.received_at
            sent_email.save()

            return Response(
                {"success": True, "message": "Reply added successfully", "reply_id": str(reply.id)},
                status=status.HTTP_201_CREATED,
            )

        except SentEmail.DoesNotExist:
            return Response({"error": "Sent email not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception("Add reply failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─── 10. Fetch Gmail Replies ───────────────────────────────────────────────
# POST /api/agent/v1/inbox/fetch-replies/
# Body: { "since_days" (optional, default 7) }

class AgentFetchRepliesView(APIView):
    """Fetch replies from Gmail inbox via OAuth or IMAP and match them to sent emails."""

    def post(self, request):
        since_days = int(request.data.get("since_days", 7))

        try:
            user = _resolve_user(request)
            if not user:
                return Response(
                    {"error": "Authentication required"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            gmail_service = None

            # Priority 1: Gmail OAuth
            try:
                from api.services.gmail_oauth_service import GmailOAuthService
                oauth_svc = GmailOAuthService(user)
                if oauth_svc.is_connected():
                    gmail_service = oauth_svc
            except Exception as exc:
                logger.warning("OAuth check failed: %s", exc)

            # Priority 2: App Password IMAP
            if not gmail_service:
                try:
                    from authentication.models import UserEmailConfig
                    cfg = UserEmailConfig.objects.get(user=user)
                    # Build IMAP reply fetcher for app-password users
                    gmail_service = _AppPasswordReplyFetcher(cfg)
                except Exception:
                    pass

            if not gmail_service:
                return Response(
                    {
                        "success": True,
                        "new_replies": 0,
                        "message": "No email account connected. Connect Gmail or set up App Password to fetch replies.",
                    },
                    status=status.HTTP_200_OK,
                )

            result = gmail_service.fetch_replies(since_days=since_days)

            # Backfill sentiment for any existing replies that were saved without it
            try:
                from api.models import EmailReply
                from api.services.gmail_reply_fetcher import GmailReplyFetcher
                _analyzer = GmailReplyFetcher()
                to_update = []
                for r in EmailReply.objects.filter(sentiment__isnull=True).exclude(body=""):
                    r.sentiment = _analyzer._analyze_sentiment(r.body)
                    to_update.append(r)
                if to_update:
                    EmailReply.objects.bulk_update(to_update, ["sentiment"])
            except Exception as _e:
                logger.warning("Sentiment backfill failed: %s", _e)

            if result.get("success"):
                return Response(
                    {
                        "success": True,
                        "message": f"Fetched {result['new_replies']} new replies",
                        "new_replies": result["new_replies"],
                        "total_processed": result.get("total_processed", 0),
                        "errors": result.get("errors", []),
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"success": False, "error": result.get("error", "Failed to fetch replies")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as exc:
            logger.exception("Fetch replies failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─── 11. Send Reply to a Received Reply ────────────────────────────────────
# POST /api/agent/v1/inbox/send-reply/
# Body: { "reply_id", "body", "subject" (optional) }

class AgentReplyToReplyView(APIView):
    """Send an email reply back to someone who replied to a campaign email."""

    def post(self, request):
        from api.models import EmailReply, SentEmail
        from api.services.gmail_oauth_service import GmailOAuthService
        from api.services.gmail_service import GmailService

        reply_id = request.data.get("reply_id")
        body = request.data.get("body")

        if not reply_id or not body:
            return Response(
                {"error": "reply_id and body are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = _resolve_user(request)
            if not user:
                return Response(
                    {"error": "Authentication required"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            try:
                reply = EmailReply.objects.select_related("sent_email").get(id=reply_id)
            except EmailReply.DoesNotExist:
                return Response({"error": "Reply not found"}, status=status.HTTP_404_NOT_FOUND)

            sent_email = reply.sent_email
            to_email = reply.from_email
            subject = request.data.get("subject") or f"Re: {sent_email.subject}"

            # Build gmail_service — same priority as send-email endpoint
            gmail_service = None

            try:
                from authentication.models import UserEmailConfig
                cfg = UserEmailConfig.objects.get(user=user)
                gmail_service = GmailService(
                    sender_email=cfg.from_email,
                    app_password=cfg.app_password,
                    smtp_host=cfg.smtp_host,
                    smtp_port=cfg.smtp_port,
                    from_name=cfg.from_name,
                )
            except Exception:
                pass

            if not gmail_service:
                oauth_service = GmailOAuthService(user)
                if oauth_service.is_connected():
                    gmail_service = oauth_service

            if not gmail_service:
                return Response(
                    {"error": "Email not configured. Please add your email settings or connect Gmail OAuth."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            result = gmail_service.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
            )

            if not result.get("success"):
                return Response(
                    {"success": False, "error": result.get("error", "Failed to send reply")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Track this outgoing reply as a SentEmail
            outgoing = SentEmail.objects.create(
                campaign_id=sent_email.campaign_id,
                step_order=sent_email.step_order,
                recipient_email=to_email,
                recipient_name=reply.from_name or to_email,
                subject=subject,
                body=body,
                sent_from=result["sender"],
                status="sent",
                metadata={
                    "in_reply_to_reply_id": str(reply.id),
                    "original_sent_email_id": str(sent_email.id),
                    "gmail_message_id": result.get("message_id"),
                },
            )

            return Response(
                {
                    "success": True,
                    "message": f"Reply sent to {to_email}",
                    "sent_email_id": str(outgoing.id),
                    "sent_to": to_email,
                    "subject": subject,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as exc:
            logger.exception("Reply to reply failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class _AppPasswordReplyFetcher:
    """Lightweight IMAP reply fetcher for users with App Password config."""

    def __init__(self, cfg):
        self.cfg = cfg

    def is_connected(self):
        return True

    def fetch_replies(self, since_days=7):
        import imaplib
        import email as email_lib
        from datetime import datetime, timedelta
        from api.models import SentEmail, EmailReply

        new_count = 0
        errors = []
        imap_host = self.cfg.smtp_host.replace("smtp.", "imap.") if self.cfg.smtp_host else "imap.gmail.com"

        try:
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(self.cfg.from_email, self.cfg.app_password)
            mail.select("INBOX")

            since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
            _, msg_ids = mail.search(None, f'(SINCE {since_date})')

            if not msg_ids[0]:
                mail.logout()
                return {"success": True, "new_replies": 0, "total_processed": 0}

            # Get subjects of sent emails to match replies
            sent_subjects = dict(
                SentEmail.objects.values_list("id", "subject")
            )
            # Build lookup: normalized subject → sent_email_id
            subject_map = {}
            for se_id, subj in sent_subjects.items():
                norm = (subj or "").lower().strip()
                for prefix in ["re: ", "re:", "fwd: ", "fwd:"]:
                    norm = norm.replace(prefix, "")
                subject_map[norm.strip()] = se_id

            total = 0
            for msg_id in msg_ids[0].split()[-100:]:  # cap at 100
                total += 1
                try:
                    _, data = mail.fetch(msg_id, "(RFC822)")
                    msg = email_lib.message_from_bytes(data[0][1])

                    from_addr = email_lib.utils.parseaddr(msg.get("From", ""))[1]
                    subj = msg.get("Subject", "")
                    norm_subj = subj.lower().strip()
                    for prefix in ["re: ", "re:", "fwd: ", "fwd:"]:
                        norm_subj = norm_subj.replace(prefix, "")
                    norm_subj = norm_subj.strip()

                    matched_se_id = subject_map.get(norm_subj)
                    if not matched_se_id:
                        continue

                    # Extract body
                    body_text = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body_text = part.get_payload(decode=True).decode("utf-8", errors="replace")
                                break
                    else:
                        body_text = msg.get_payload(decode=True).decode("utf-8", errors="replace")

                    # Check if reply already exists
                    exists = EmailReply.objects.filter(
                        sent_email_id=matched_se_id,
                        from_email=from_addr,
                        body=body_text[:500],
                    ).exists()

                    if not exists:
                        se = SentEmail.objects.get(id=matched_se_id)
                        EmailReply.objects.create(
                            sent_email=se,
                            from_email=from_addr,
                            from_name=email_lib.utils.parseaddr(msg.get("From", ""))[0],
                            subject=subj,
                            body=body_text,
                            is_read=False,
                        )
                        se.status = "replied"
                        se.replied_at = se.replied_at or datetime.now()
                        se.save(update_fields=["status", "replied_at"])
                        new_count += 1

                except Exception as e:
                    errors.append(str(e))

            mail.logout()
            return {"success": True, "new_replies": new_count, "total_processed": total, "errors": errors[:5]}

        except Exception as exc:
            logger.warning("IMAP fetch failed: %s", exc)
            return {"success": False, "error": str(exc), "new_replies": 0}

# ─── Business Profile GET/POST ────────────────────────────────────────────────
# GET  /api/agent/v1/business-profile/  → returns current profile or {}
# POST /api/agent/v1/business-profile/  → create or update profile

class AgentBusinessProfileView(APIView):

    def get(self, request):
        try:
            user = _resolve_user(request)
            if not user:
                return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

            from api.models import BusinessProfile
            profile = BusinessProfile.objects.filter(account_id=user.account_id).first()
            if not profile:
                return Response({})

            return Response({
                "name": profile.name or "",
                "description": profile.description or "",
                "industry": profile.industry or "",
                "website": profile.website or "",
                "services": ", ".join(profile.services) if isinstance(profile.services, list) else (profile.services or ""),
                "brand_voice": profile.brand_voice or "",
                "tone_preferences": profile.tone_preferences.get("preferred", "") if isinstance(profile.tone_preferences, dict) else (profile.tone_preferences or ""),
                "employee_count": profile.employee_count or "",
            })
        except Exception as e:
            logger.error("BusinessProfile GET error: %s", e, exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            user = _resolve_user(request)
            if not user:
                return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

            from api.models import BusinessProfile
            import uuid

            data = request.data
            services_raw = data.get("services", "")
            services = [s.strip() for s in services_raw.split(",") if s.strip()] if services_raw else []
            tone_raw = data.get("tone_preferences", "")
            tone = {"preferred": tone_raw} if tone_raw else {}

            profile = BusinessProfile.objects.filter(account_id=user.account_id).first()
            if profile:
                profile.name = data.get("name", profile.name)
                profile.description = data.get("description", profile.description)
                profile.industry = data.get("industry", profile.industry)
                profile.website = data.get("website", profile.website)
                profile.brand_voice = data.get("brand_voice", profile.brand_voice)
                profile.employee_count = data.get("employee_count", profile.employee_count)
                if services:
                    profile.services = services
                if tone_raw:
                    profile.tone_preferences = tone
                profile.save()
            else:
                profile = BusinessProfile.objects.create(
                    id=uuid.uuid4().hex,
                    account_id=user.account_id,
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                    industry=data.get("industry", ""),
                    website=data.get("website", ""),
                    brand_voice=data.get("brand_voice", ""),
                    employee_count=data.get("employee_count", ""),
                    services=services,
                    tone_preferences=tone,
                )

            return Response({"success": True})
        except Exception as e:
            logger.error("BusinessProfile POST error: %s", e, exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
