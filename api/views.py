# api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


class LeadUploadView(APIView):
    """
    POST /leads/upload/ (multipart/form-data)
    Imports leads from an uploaded .csv or .xlsx file. Leads are upserted
    by email (channel="upload"). No external lead-data API is called.

    Every upload is grouped into a LeadList (auto-named if lead_list_name
    isn't given), so the resulting leads can always be found later.

    Form fields:
        file             - required, the .csv/.xlsx file
        lead_list_name   - optional, name for a new LeadList
        owner_user_id    - optional
        session_id       - optional, the chat session this upload belongs to.
                            When given, the resulting lead_list_id is saved onto
                            that session's state (so campaign creation in this
                            chat picks it up automatically), and repeat uploads
                            in the same chat append to the same list instead of
                            creating a new one each time.
    """
    def post(self, request):
        from .models import ConversationSession
        from .services.lead_upload_service import import_leads

        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

        lead_list_name = request.data.get("lead_list_name") or None
        owner_user_id = request.data.get("owner_user_id") or None
        session_id = request.data.get("session_id") or None

        session = None
        existing_lead_list_id = None
        if session_id:
            try:
                session = ConversationSession.objects.get(session_id=session_id)
                existing_lead_list_id = (session.state or {}).get("lead_list_id")
            except ConversationSession.DoesNotExist:
                return Response({"error": "session not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = import_leads(
                upload,
                upload.name,
                lead_list_name=lead_list_name,
                owner_user_id=owner_user_id,
                existing_lead_list_id=existing_lead_list_id,
            )
            if session is not None and result.get("lead_list_id"):
                state = session.state or {}
                state["lead_list_id"] = result["lead_list_id"]
                session.state = state
                session.save(update_fields=["state", "updated_at"])

            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Lead Upload Failed: {e}", exc_info=True)
            return Response({"error": "An unexpected error occurred during lead upload."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
