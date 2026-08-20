from django.test import SimpleTestCase
from django.urls import resolve

from agent_runtime.mapping.response_mapper import map_message_result
from agent_runtime.orchestrator.state_machine import FlowStateMachine


class ResponseMapperTests(SimpleTestCase):
    def test_maps_frontend_contract_fields(self):
        result = {
            "text": "hello",
            "current_flow": "lead_search",
            "past_flows": ["chit_chat"],
            "future_flows": [{"flow": "people_search_api", "url": "/api/agent/v1/leads/search/people/"}],
            "campaign_status": "ai_generated",
            "campaign_context": {"a": 1},
            "state": {"slots": {"title": "cto"}},
        }
        mapped = map_message_result(result)
        self.assertEqual(mapped["reply"], "hello")
        self.assertEqual(mapped["current_flow"], "lead_search")
        self.assertEqual(mapped["slots"], {"title": "cto"})
        self.assertEqual(mapped["campaign_status"], "ai_generated")

    def test_maps_optional_provider_fields(self):
        result = {
            "text": "ok",
            "search_parameters": {"title": "cto"},
            "provider_metadata": {"provider": "zoominfo"},
        }
        mapped = map_message_result(result)
        self.assertEqual(mapped["search_parameters"]["title"], "cto")
        self.assertEqual(mapped["provider_metadata"]["provider"], "zoominfo")


class StateMachineTests(SimpleTestCase):
    def test_clarification_threshold(self):
        state = {}
        self.assertTrue(FlowStateMachine.can_ask_clarification(state))
        state = FlowStateMachine.increment_clarification(state)
        state = FlowStateMachine.increment_clarification(state)
        self.assertFalse(FlowStateMachine.can_ask_clarification(state))


class EndpointResolutionTests(SimpleTestCase):
    def test_agent_message_route_exists(self):
        match = resolve("/api/agent/v1/conversation/message/")
        self.assertEqual(match.func.view_class.__name__, "AgentConversationMessageView")
