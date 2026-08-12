"""
AgentLogger — writes structured action logs to AgentConversationEvent.

Usage:
    logger = AgentLogger(session, turn_id="abc123")
    logger.log_intent(intent="lead_search", confidence=0.95)
    logger.log_agent_selected(agent="lead_search_agent")
    logger.log_llm_call(actor="campaign_agent", model="gpt-4o-mini", prompt_tokens=210)
    logger.log_response(actor="campaign_agent", text="Here is your campaign...")
    logger.log_error(actor="campaign_agent", error="OpenAI timeout")
"""

import threading
from agent_runtime.persistence.models import AgentConversationSession, AgentConversationEvent

import logging
logger = logging.getLogger(__name__)


class AgentLogger:
    """Thread-safe logger that writes agent actions to AgentConversationEvent."""

    def __init__(self, session: AgentConversationSession, turn_id: str):
        self.session = session
        self.turn_id = turn_id
        self._seq = 0
        self._lock = threading.Lock()

    # ── Core write ────────────────────────────────────────────────────────────

    def log(self, event_type: str, actor: str, payload: dict | None = None):
        with self._lock:
            self._seq += 1
            seq_no = self._seq

        try:
            AgentConversationEvent.objects.create(
                session=self.session,
                turn_id=self.turn_id,
                seq_no=seq_no,
                event_type=event_type,
                actor=actor,
                payload_json=payload or {},
            )
        except Exception as e:
            # Never let logging crash the agent
            logger.warning("AgentLogger.log failed: %s", e)

    # ── Convenience methods ───────────────────────────────────────────────────

    def log_intent(self, intent: str, confidence: float | None = None, raw_text: str | None = None):
        self.log(
            event_type="intent_routed",
            actor="intent_router",
            payload={"intent": intent, "confidence": confidence, "raw_text": raw_text},
        )

    def log_agent_selected(self, agent: str, intent: str, active_flow: str | None = None):
        self.log(
            event_type="agent_selected",
            actor="root_orchestrator",
            payload={"agent": agent, "intent": intent, "active_flow": active_flow},
        )

    def log_llm_call(self, actor: str, model: str, prompt_tokens: int | None = None, extra: dict | None = None):
        payload = {"model": model, "prompt_tokens": prompt_tokens}
        if extra:
            payload.update(extra)
        self.log(event_type="llm_call", actor=actor, payload=payload)

    def log_llm_response(self, actor: str, completion_tokens: int | None = None, finish_reason: str | None = None):
        self.log(
            event_type="llm_response",
            actor=actor,
            payload={"completion_tokens": completion_tokens, "finish_reason": finish_reason},
        )

    def log_response(self, actor: str, text: str | None = None, extra: dict | None = None):
        payload = {"text": (text or "")[:500]}  # cap stored text at 500 chars
        if extra:
            payload.update(extra)
        self.log(event_type="agent_response", actor=actor, payload=payload)

    def log_action(self, actor: str, action: str, detail: dict | None = None):
        self.log(
            event_type="agent_action",
            actor=actor,
            payload={"action": action, **(detail or {})},
        )

    def log_error(self, actor: str, error: str, detail: dict | None = None):
        self.log(
            event_type="error",
            actor=actor,
            payload={"error": str(error), **(detail or {})},
        )
