from agent_runtime.tools.providers.provider_contract import ProviderContract


class ZoomInfoProvider(ProviderContract):
    """
    Stub provider for future multi-source expansion.
    Replace this with real ZoomInfo API integration when requirements are finalized.
    """

    source_name = "zoominfo"

    def search_people(self, params: dict, session_id: str | None = None, account_id: str | None = None) -> dict:
        return {
            "people": [],
            "total_entries": 0,
            "search_parameters": dict(params or {}),
            "provider_status": "stub_not_implemented",
            "message": "ZoomInfo provider is registered as a stub and is not enabled for production queries yet.",
        }
