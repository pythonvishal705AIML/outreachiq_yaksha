import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from agent_runtime.agents.campaign_agent import CampaignAgent
from agent_runtime.agents.chitchat_agent import ChitChatAgent
from agent_runtime.agents.lead_search_agent import LeadSearchAgent
from agent_runtime.orchestrator.intent_router_agent import IntentRouterAgent
from agent_runtime.agent_logger import AgentLogger


class RootOrchestratorAgent:
    """
    Agents are created lazily — only the one that actually handles the turn
    pays the init cost (ChitChatAgent does a DB query on __init__).
    """

    def __init__(self, session):
        self.session = session
        self.intent_router = IntentRouterAgent()
        self._lead_agent = None
        self._campaign_agent = None
        self._chit_chat_agent = None

    # ── Lazy agent accessors ──────────────────────────────────────────────────

    @property
    def lead_agent(self) -> LeadSearchAgent:
        if self._lead_agent is None:
            self._lead_agent = LeadSearchAgent(self.session)
        return self._lead_agent

    @property
    def campaign_agent(self) -> CampaignAgent:
        if self._campaign_agent is None:
            self._campaign_agent = CampaignAgent(self.session)
        return self._campaign_agent

    @property
    def chit_chat_agent(self) -> ChitChatAgent:
        if self._chit_chat_agent is None:
            self._chit_chat_agent = ChitChatAgent(self.session)
        return self._chit_chat_agent

    # ── Routing helpers ───────────────────────────────────────────────────────

    def _agent_for_intent(self, intent: str, active_flow: str):
        """Map intent + active flow to the right agent."""
        if intent in ("chit_chat", "unknown"):
            return self.chit_chat_agent
        if intent == "create_campaign":
            return self.campaign_agent
        if intent == "lead_search":
            return self.lead_agent
        # Fallback: resume active flow
        if active_flow == "campaign_flow":
            return self.campaign_agent
        if active_flow == "lead_search":
            return self.lead_agent
        return self.chit_chat_agent

    # ── Public turn handlers ──────────────────────────────────────────────────

    def handle_turn(self, user_text: str, history: list[dict]) -> dict:
        state = self.session.state or {}
        active_flow = state.get("flow")
        turn_id = str(uuid.uuid4())
        agent_log = AgentLogger(self.session, turn_id)

        # Fix 6: run intent routing in a thread while we warm the campaign agent
        # (safe: _ensure_campaign is a read when campaign already exists)
        with ThreadPoolExecutor(max_workers=2) as ex:
            intent_fut: Future = ex.submit(self.intent_router.route, history)

            # Pre-warm campaign DB lookup only when campaign_id is already in state
            # (guarantees _ensure_campaign is a pure read, no state side-effects)
            if active_flow == "campaign_flow" and state.get("campaign_id"):
                ex.submit(self.campaign_agent._ensure_campaign)

            intent = intent_fut.result()

        agent_log.log_intent(intent=intent, raw_text=user_text)
        agent = self._agent_for_intent(intent, active_flow)
        agent_log.log_agent_selected(
            agent=type(agent).__name__,
            intent=intent,
            active_flow=active_flow,
        )

        try:
            result = agent.handle(user_text, history, agent_log=agent_log)
            agent_log.log_response(actor=type(agent).__name__, text=result.get("text"))
            return result
        except Exception as e:
            agent_log.log_error(actor=type(agent).__name__, error=str(e))
            raise

    def _resolve_agent(self, user_text: str, history: list[dict]):
        """Return (agent, agent_log, turn_id) for this turn."""
        state = self.session.state or {}
        active_flow = state.get("flow")
        turn_id = str(uuid.uuid4())
        agent_log = AgentLogger(self.session, turn_id)

        with ThreadPoolExecutor(max_workers=2) as ex:
            intent_fut: Future = ex.submit(self.intent_router.route, history)
            if active_flow == "campaign_flow" and state.get("campaign_id"):
                ex.submit(self.campaign_agent._ensure_campaign)
            intent = intent_fut.result()

        agent_log.log_intent(intent=intent, raw_text=user_text)
        agent = self._agent_for_intent(intent, active_flow)
        agent_log.log_agent_selected(
            agent=type(agent).__name__,
            intent=intent,
            active_flow=active_flow,
        )
        return agent, agent_log

    def handle_turn_stream(self, user_text: str, history: list[dict]):
        """Generator: yields streaming events from the resolved agent."""
        agent, agent_log = self._resolve_agent(user_text, history)
        yield from agent.handle_stream(user_text, history, agent_log=agent_log)
