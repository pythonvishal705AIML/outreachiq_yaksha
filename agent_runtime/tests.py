from django.test import SimpleTestCase
from django.urls import resolve

from agent_runtime.mapping.response_mapper import map_message_result
from agent_runtime.orchestrator.state_machine import FlowStateMachine
from agent_runtime.tools.providers.provider_ranker import ProviderRanker
from agent_runtime.tools.providers.provider_selector import ProviderSelector


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


class ProviderSelectorTests(SimpleTestCase):
    def test_selects_requested_default_provider(self):
        provider, reason = ProviderSelector().select("primary_provider", ["primary_provider", "zoominfo"])
        self.assertEqual(provider, "primary_provider")
        self.assertEqual(reason, "requested_by_user")

    def test_falls_back_to_default(self):
        provider, reason = ProviderSelector().select(None, ["primary_provider", "zoominfo"])
        self.assertEqual(provider, "primary_provider")
        self.assertEqual(reason, "default_source")

    def test_non_default_requires_explicit_opt_in(self):
        provider, reason = ProviderSelector().select("zoominfo", ["primary_provider", "zoominfo"])
        self.assertEqual(provider, "primary_provider")
        self.assertEqual(reason, "default_source")

        provider, reason = ProviderSelector().select(
            "zoominfo",
            ["primary_provider", "zoominfo"],
            allow_non_default=True,
        )
        self.assertEqual(provider, "zoominfo")
        self.assertEqual(reason, "requested_by_user")

    def test_raises_when_no_providers_configured(self):
        with self.assertRaises(ValueError):
            ProviderSelector().select(None, [])


class ProviderRankerTests(SimpleTestCase):
    def test_deduplicates_people_rows(self):
        rows = [
            {"id": "1", "name": "A"},
            {"id": "1", "name": "A2"},
            {"id": "2", "name": "B"},
        ]
        deduped = ProviderRanker().dedupe_people(rows)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["id"], "1")
        self.assertEqual(deduped[1]["id"], "2")


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

    def test_agent_people_search_route_exists(self):
        match = resolve("/api/agent/v1/leads/search/people/")
        self.assertEqual(match.func.view_class.__name__, "AgentPeopleSearchView")
