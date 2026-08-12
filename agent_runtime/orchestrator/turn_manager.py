import uuid

from api.models import ConversationMessage, ConversationSession
from api.services.main_service import APIService
from agent_runtime.orchestrator.root_agent import RootOrchestratorAgent
from agent_runtime.persistence.repository import AgentRepository
from agent_runtime.tools.lead_source_router import LeadSourceRouter


class TurnManager:
    def __init__(self, session_id: str | None = None, auto_create: bool = False, tenant_id: str | None = None):
        self.session = None
        self.session_id = session_id
        if session_id:
            self.session = ConversationSession.objects.get(session_id=session_id)
        elif auto_create and tenant_id:
            self.session_id = APIService.init_conversation_session(tenant_id=tenant_id, initial_text="")
            self.session = ConversationSession.objects.get(session_id=self.session_id)

        if self.session:
            AgentRepository.ensure_session(self.session_id, self.session.tenant_id)

    MAX_HISTORY = 10  # Cap context window — shorter input → faster LLM response

    def _history(self) -> list[dict]:
        recent = self.session.messages.order_by("-timestamp")[:self.MAX_HISTORY]
        return [
            {"role": msg.role, "content": msg.text}
            for msg in reversed(recent)  # chronological order
        ]

    def run_message_turn(self, user_text: str) -> dict:
        turn_id = str(uuid.uuid4())
        AgentRepository.log_event(self.session_id, turn_id, "message.user.received", "user", {"text": user_text})

        ConversationMessage.objects.create(session=self.session, role="user", text=user_text)
        result = RootOrchestratorAgent(self.session).handle_turn(user_text=user_text, history=self._history())

        bot_text = result.get("reply") or result.get("text") or "Campaign created successfully."
        ConversationMessage.objects.create(
            session=self.session,
            role="assistant",
            text=bot_text,
            metadata=result.get("parameters", {}),
        )

        AgentRepository.log_event(
            self.session_id,
            turn_id,
            "message.assistant.generated",
            "assistant",
            {"text": bot_text, "result": result},
        )
        AgentRepository.update_state(self.session_id, self.session.state or {})
        AgentRepository.log_event(self.session_id, turn_id, "turn.completed", "system", {})
        result["reply"] = bot_text
        return result

    def run_people_search(self, params: dict, channel: str | None = None, account_id: str | None = None) -> dict:
        turn_id = str(uuid.uuid4())
        if self.session_id:
            AgentRepository.log_event(
                self.session_id,
                turn_id,
                "source.selection.completed",
                "system",
                {"requested_channel": channel},
            )
        payload = LeadSourceRouter().search_people(
            params=params,
            preferred_source=channel,
            session_id=self.session_id,
            account_id=account_id,
        )
        if self.session_id:
            AgentRepository.log_event(
                self.session_id,
                turn_id,
                "source.query.executed",
                "tool",
                {"search_parameters": params, "provider": payload.get("provider_metadata", {}).get("provider")},
            )
            AgentRepository.log_event(
                self.session_id,
                turn_id,
                "source.result.normalized",
                "tool",
                {
                    "count": len(payload.get("people", [])),
                    "search_run_id": str(payload.get("search_run_id") or ""),
                    "lead_ids": [row.get("lead_id") for row in payload.get("people", []) if row.get("lead_id")],
                },
            )
        return payload

    def run_message_turn_stream(self, user_text: str):
        """
        Generator version of run_message_turn.
        Yields streaming events: {"type": "token", "text": "..."} and {"type": "result", "data": {...}}
        Persists messages and logs after streaming completes.
        """
        turn_id = str(uuid.uuid4())
        AgentRepository.log_event(self.session_id, turn_id, "message.user.received", "user", {"text": user_text})
        ConversationMessage.objects.create(session=self.session, role="user", text=user_text)

        orchestrator = RootOrchestratorAgent(self.session)
        result_data = None

        for event in orchestrator.handle_turn_stream(user_text=user_text, history=self._history()):
            if event.get("type") == "result":
                result_data = event["data"]
            yield event

        # Persist after stream completes
        if result_data:
            bot_text = result_data.get("reply") or result_data.get("text") or "Campaign created successfully."
            ConversationMessage.objects.create(
                session=self.session,
                role="assistant",
                text=bot_text,
                metadata=result_data.get("parameters", {}),
            )
            AgentRepository.log_event(
                self.session_id, turn_id, "message.assistant.generated", "assistant",
                {"text": bot_text, "result": result_data},
            )
            AgentRepository.update_state(self.session_id, self.session.state or {})
            AgentRepository.log_event(self.session_id, turn_id, "turn.completed", "system", {})
