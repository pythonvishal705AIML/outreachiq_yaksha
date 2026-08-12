# Agent Runtime Changelog

## 2026-03-31

### Added
- Multi-source provider framework with default Apollo + ZoomInfo stub registration.
- Provider selector safety policy requiring explicit opt-in for non-default providers.
- `next_action` response hint for frontend-triggered people-search API calls.
- Conversation history enrichment with `search_runs` context and lead previews.
- `conversation_lifecycle.md` for event/write timeline.

### Updated
- `conversation/init` supports `org_id` in addition to `tenant_id`.
- Campaign flow changed to clarification-first behavior before generation.
- Campaign context now includes organization profile data when available.

### Notes
- Existing `api/` endpoints remain untouched.
- Agent runtime routes are mounted under `/api/agent/v1/`.
