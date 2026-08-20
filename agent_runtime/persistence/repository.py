from django.db import transaction
from django.db.models import Max

from api.models import ConversationSession
from agent_runtime.persistence.models import (
    AgentConversationEvent,
    AgentConversationSession,
    AgentConversationState,
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
    def get_full_history(session_id: str):
        try:
            base_session = ConversationSession.objects.get(session_id=session_id)
        except ConversationSession.DoesNotExist:
            return None

        events = []
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

        return {
            "session_id": session_id,
            "state": state,
            "messages": messages,
            "events": events,
        }
