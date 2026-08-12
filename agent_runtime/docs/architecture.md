# Agent Runtime Architecture

## Goal
Build an agent-first conversation system that preserves the existing frontend response contract while enabling incremental internal upgrades.

## High-level Flow
1. Client calls `api/agent/v1/conversation/message/`.
2. `TurnManager` logs user event and delegates to `RootOrchestratorAgent`.
3. Intent router chooses flow (`lead_search`, `campaign_flow`, `chit_chat`).
4. Sub-agent executes tools and updates state.
5. Campaign flow runs in two stages:
   - clarification-first (asks missing goal/audience/tone context),
   - generation (campaign + emails) once clarification returns `ready_for_generation`.
5. Assistant response + events are persisted.
6. Response is mapped to existing frontend format.

## Modules
- `api/`: DRF views and endpoint routing.
- `orchestrator/`: turn lifecycle, routing, anti-loop state machine.
- `agents/`: flow-specific agent logic.
- `tools/`: provider router and flow tools.
- `persistence/`: normalized event/state/session data layer.
- `mapping/`: response compatibility mapper.

## Response Contract (must stay stable)
- `reply`
- `current_flow`
- `past_flows`
- `future_flows`
- `campaign_status`
- `campaign_context`
- `slots`
- optional lead-source fields: `search_parameters`, `provider_metadata`
- orchestration hint for FE: `next_action` (for example trigger people search API call)

## Org Context
- `conversation/init` accepts `tenant_id` or `org_id`.
- `org_id` is used as tenant/account context for the session.
- Campaign generation context includes organization profile attributes from `BusinessProfile` when available.

## Event Sourcing
Core tables:
- `agent_conversation_sessions`
- `agent_conversation_events`
- `agent_conversation_states`
- `agent_source_execution_audits`

The history endpoint replays full messages + events + source audits.
It also includes `search_runs` summary so side chat can display prior search context and lead previews.
