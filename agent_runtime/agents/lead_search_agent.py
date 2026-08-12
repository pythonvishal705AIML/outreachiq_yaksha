from api.services.lead_extractor import LeadParameterExtractor
from agent_runtime.orchestrator.state_machine import FlowStateMachine


class LeadSearchAgent:
    def __init__(self, session):
        self.session = session
        self.extractor = LeadParameterExtractor()

    def handle(self, user_text: str, history: list[dict], agent_log=None) -> dict:
        if agent_log:
            agent_log.log_action(actor="lead_search_agent", action="extract_parameters")
        # extracted = self.extractor.extract(user_text, business_context="")
        extracted = self.extractor.extract(business_data={}, user_query=user_text, history=history)
        slots = extracted.get("filters") or extracted.get("parameters") or {}

        state = self.session.state or {}
        if not slots:
            if FlowStateMachine.can_ask_clarification(state):
                state = FlowStateMachine.increment_clarification(state)
                self.session.state = state
                self.session.save(update_fields=["state", "updated_at"])
                return {
                    "text": (
                        "Please share role, location, and industry so I can search your uploaded leads. "
                        "Note: no external lead-data provider is connected right now, so results are "
                        "limited to leads you've imported via Upload Leads."
                    ),
                    "state": {"slots": state.get("slots", {})},
                    "current_flow": "lead_search",
                    "past_flows": state.get("past_flows", []),
                    "future_flows": [{"flow": "people_search_api", "url": "/api/agent/v1/leads/search/people/"}],
                    "next_action": {"type": "call_api", "endpoint": "/api/agent/v1/leads/search/people/"},
                }
            default_slots = {"location": "US", "industry": "SaaS", "title": "Leadership"}
            state.update({"flow": "lead_search", "step": "confirm_search_params", "slots": default_slots})
            self.session.state = state
            self.session.save(update_fields=["state", "updated_at"])
            return {
                "text": (
                    "I will use defaults: US SaaS leadership personas. You can refine this before search. "
                    "Note: no external lead-data provider is connected right now, so results are limited "
                    "to leads you've imported via Upload Leads."
                ),
                "parameters": default_slots,
                "state": {"slots": default_slots},
                "current_flow": "lead_search",
                "past_flows": state.get("past_flows", []),
                "future_flows": [{"flow": "people_search_api", "url": "/api/agent/v1/leads/search/people/"}],
                "next_action": {"type": "call_api", "endpoint": "/api/agent/v1/leads/search/people/"},
            }

        state.update({"flow": "lead_search", "step": "confirm_search_params", "slots": slots})
        self.session.state = state
        self.session.save(update_fields=["state", "updated_at"])

        return {
            "text": (
                "I captured your lead search parameters. You can run people search now — note it will "
                "only search leads you've already imported via Upload Leads, since no external "
                "lead-data provider is connected."
            ),
            "parameters": slots,
            "state": {"slots": slots},
            "current_flow": "lead_search",
            "past_flows": state.get("past_flows", []),
            "future_flows": [{"flow": "people_search_api", "url": "/api/agent/v1/leads/search/people/"}],
            "next_action": {"type": "call_api", "endpoint": "/api/agent/v1/leads/search/people/"},
        }

    def handle_stream(self, user_text: str, history: list[dict], agent_log=None):
        """Non-streaming agent — yields final result as single event."""
        result = self.handle(user_text, history, agent_log=agent_log)
        yield {"type": "token", "text": result.get("text", "")}
        yield {"type": "result", "data": result}
