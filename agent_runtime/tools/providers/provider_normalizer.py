class ProviderNormalizer:
    def normalize_people_response(self, payload: dict, provider: str, selection_reason: str) -> dict:
        output = dict(payload or {})
        output.setdefault("people", [])
        output["provider_metadata"] = {
            "provider": provider,
            "selection_reason": selection_reason,
        }
        output.setdefault("search_parameters", {})
        return output
