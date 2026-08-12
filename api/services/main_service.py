import uuid

from ..models import ConversationSession, ConversationMessage
from .orchestrator import ConversationOrchestrator


class APIService:

    @staticmethod
    def handle_conversation_message(session_id, user_text):

        session = ConversationSession.objects.get(session_id=session_id)

        # Save user text first
        ConversationMessage.objects.create(session=session, role="user", text=user_text)

        # Run orchestrator
        orchestrator = ConversationOrchestrator(session)
        result = orchestrator.handle_message(user_text)

        # Result is a dict: {"text": "...", "parameters": {...}}
        bot_text = result.get("text", "") or ""
        if not bot_text:
            bot_text = "I'm here to help! Could you tell me what you're looking for? I can find leads or help build outreach campaigns."
        params = result.get("parameters") or {}

        # Ensure result carries the (possibly fallback) bot_text
        result["text"] = bot_text

        # Persist the assistant reply with metadata (e.g. search params)
        ConversationMessage.objects.create(
            session=session, 
            role="assistant", 
            text=bot_text,
            metadata=params
        )

        # Return full structure including params
        return result


    @staticmethod
    def init_conversation_session(tenant_id, initial_text):
        session_id = str(uuid.uuid4())

        session = ConversationSession.objects.create(
            tenant_id=tenant_id,
            session_id=session_id,
            state={}
        )

        if initial_text:
            ConversationMessage.objects.create(
                session=session,
                role="user",
                text=initial_text
            )

        return session_id

    @staticmethod
    def session_history(session_id):
        try:
            session = ConversationSession.objects.get(session_id=session_id)
        except ConversationSession.DoesNotExist:
            return {"error": "Invalid session_id"},

        messages = session.messages.order_by("timestamp")

        # Re-calculate flow status (especially future_flows which is dynamic)
        try:
            orchestrator = ConversationOrchestrator(session)
            flow_status = orchestrator._get_flow_status()
        except Exception as e:
            # Fallback if orchestrator fails (e.g., during migration)
            flow_status = {}

        # Filter redundant past_flows from state for display
        display_state = session.state.copy()
        display_state.pop("past_flows", None)

        response = {
                "session_id": session_id,
                "state": display_state,
                "current_flow": flow_status.get("current_flow"),
                "past_flows": flow_status.get("past_flows", []),
                "future_flows": flow_status.get("future_flows", []),
                "messages": [
                    {
                        "role": msg.role,
                        "text": msg.text,
                        "timestamp": msg.timestamp,
                        "metadata": msg.metadata if msg.metadata else {}
                    }
                    for msg in messages
                ]
            }
        
        return response


    @staticmethod
    def reset_conversation_session(session_id):
        try:
            session = ConversationSession.objects.get(session_id=session_id)
            session.state = {}
            session.save()
        except ConversationSession.DoesNotExist:
            return {"error": "Invalid session_id"}


