import time

from agent_runtime.persistence.repository import AgentRepository
from agent_runtime.tools.providers.provider_normalizer import ProviderNormalizer
from agent_runtime.tools.providers.provider_ranker import ProviderRanker
from agent_runtime.tools.providers.provider_selector import ProviderSelector
from agent_runtime.tools.providers.zoominfo_provider import ZoomInfoProvider


class LeadSourceRouter:
    def __init__(self):
        # No external lead-data provider is currently configured. "zoominfo"
        # remains registered as the future-expansion stub it always was
        # (see ZoomInfoProvider) — it responds with provider_status
        # "stub_not_implemented" until a real integration is added.
        self.providers = {
            "zoominfo": ZoomInfoProvider(),
        }
        self.selector = ProviderSelector()
        self.normalizer = ProviderNormalizer()
        self.ranker = ProviderRanker()

    def search_people(
        self,
        params: dict,
        preferred_source: str | None = None,
        session_id: str | None = None,
        account_id: str | None = None,
    ) -> dict:
        allow_non_default = bool((params or {}).get("allow_non_default_provider"))
        source, reason = self.selector.select(
            preferred_source=preferred_source,
            available_sources=list(self.providers.keys()),
            allow_non_default=allow_non_default,
        )
        provider = self.providers[source]
        _t_start = time.perf_counter()
        results = provider.search_people(params=params, session_id=session_id, account_id=account_id)
        _total_ms = round((time.perf_counter() - _t_start) * 1000)
        latency = results.get("_search_latency", {})
        print(
            f"\n[Lead Source Timing] provider={source} total={_total_ms}ms | "
            f"api_queries={latency.get('queries_ms', 'N/A')}ms | "
            f"normalization={latency.get('normalization_ms', 'N/A')}ms | "
            f"queries_executed={latency.get('queries_executed', 'N/A')} | "
            f"leads_found={len(results.get('people', []))}\n"
        )
        results = self.normalizer.normalize_people_response(results, provider=source, selection_reason=reason)
        # Dedupe but don't limit - return all collected leads
        results["people"] = self.ranker.dedupe_people(results.get("people", []))

        if session_id:
            AgentRepository.log_source_execution(
                session_id=session_id,
                provider=source,
                request_payload=results.get("search_parameters", {}),
                response_count=len(results.get("people", [])),
                status="completed",
            )
        return results
