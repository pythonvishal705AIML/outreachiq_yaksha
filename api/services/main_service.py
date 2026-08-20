import uuid

from ..models import ConversationSession, ConversationMessage


class APIService:

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
    def reset_conversation_session(session_id):
        try:
            session = ConversationSession.objects.get(session_id=session_id)
            session.state = {}
            session.save()
        except ConversationSession.DoesNotExist:
            return {"error": "Invalid session_id"}
