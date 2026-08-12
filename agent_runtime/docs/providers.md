# Provider Integration Guide

## Current State
- Default provider: `apollo`
- Registered stub provider: `zoominfo` (not production-enabled)

## Selection Policy
Apollo is selected by default.
Non-default providers are used only when:
1. `preferred_source` matches a registered provider, and
2. request params include `allow_non_default_provider=true`.

This safety policy avoids accidental source switching.

## Frontend Impact
- Response remains backward-compatible.
- Provider provenance is available in `provider_metadata`.
- Search API payload includes `search_run_id` (from service) for history/replay correlation.

## Provider Contract
All providers must implement:
- `search_people(params, session_id=None, account_id=None) -> dict`

Expected response fields:
- `people` (list)
- `search_parameters` (dict)
- optional provider-specific fields

## Add a New Provider
1. Create `tools/providers/<provider>_provider.py`.
2. Implement `ProviderContract`.
3. Register provider in `LeadSourceRouter.providers`.
4. Add selector tests and normalization tests.
5. Keep response schema backward-compatible.
