class ProviderSelector:
    def select(
        self,
        preferred_source: str | None,
        available_sources: list[str],
        allow_non_default: bool = False,
    ) -> tuple[str, str]:
        if not available_sources:
            raise ValueError("No lead-search providers are configured.")
        if preferred_source and preferred_source in available_sources:
            if allow_non_default or preferred_source == available_sources[0]:
                return preferred_source, "requested_by_user"
            return available_sources[0], "default_source"
        return available_sources[0], "default_source"
