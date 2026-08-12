# Agent Runtime Operations

## Rollout Controls
Configured in `project/settings.py`:
- `AGENT_RUNTIME_ENABLED`
- `AGENT_RUNTIME_TENANT_ALLOWLIST`

Use allowlist for tenant-by-tenant rollout.

## Key Endpoints
- `POST /api/agent/v1/conversation/init/`
- `POST /api/agent/v1/conversation/message/`
- `POST /api/agent/v1/conversation/history/`
- `POST /api/agent/v1/conversation/reset/`
- `POST /api/agent/v1/leads/search/people/`

`conversation/init` accepts either `tenant_id` or `org_id`.

## History and Debugging
Use conversation history endpoint to inspect:
- chronological messages
- orchestration/tool events
- source execution audits
- reduced state snapshot
- `search_runs` context (run IDs, filters, lead preview, status/full-results URLs)

## Frontend Trigger Convention
- During lead-search orchestration, assistant response can include:
  - `next_action.type = call_api`
  - `next_action.endpoint = /api/agent/v1/leads/search/people/`
- Frontend should call people-search API when this hint is present.

## Safe Change Checklist
1. Keep old `api/` endpoints untouched.
2. Preserve response contract in mapper.
3. Add tests for new routes or provider behavior.
4. Validate event persistence for each turn.
