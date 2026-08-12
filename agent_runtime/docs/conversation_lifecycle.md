# Conversation Lifecycle

## Purpose
Defines the per-turn execution timeline for `agent_runtime`, including event emission and DB persistence expectations.

## Turn Timeline (Message Endpoint)

1. Request received at `POST /api/agent/v1/conversation/message/`
2. `TurnManager.run_message_turn()` starts
3. Persist user message event
4. Persist user `ConversationMessage`
5. Route through `RootOrchestratorAgent`
6. Execute selected sub-agent (`lead_search`, `campaign_flow`, `chit_chat`)
   - for `campaign_flow`, run clarification-first and ask missing context when needed
7. Persist assistant `ConversationMessage`
8. Persist assistant event + turn completion event
9. Update reduced state snapshot
10. Map output to frontend-compatible response

## Event Matrix

| Order | Event Type | Actor | Typical Payload | Storage |
|---|---|---|---|---|
| 1 | `message.user.received` | `user` | `{ text }` | `agent_conversation_events` |
| 2 | `message.assistant.generated` | `assistant` | `{ text, result }` | `agent_conversation_events` |
| 3 | `turn.completed` | `system` | `{}` | `agent_conversation_events` |

If an exception path is added, emit `turn.failed` with error metadata (sanitized for user output).

## Source Search Timeline (People Search Endpoint)

1. Request received at `POST /api/agent/v1/leads/search/people/`
2. Provider selection executed in `LeadSourceRouter`
3. Provider query executed (`apollo` default unless non-default explicitly enabled)
4. Result normalized and de-duplicated
5. Source audit row persisted (if `session_id` exists)
6. Source events persisted (if `session_id` exists)

### Source Events

| Order | Event Type | Actor | Typical Payload |
|---|---|---|---|
| 1 | `source.selection.completed` | `system` | `{ requested_channel }` |
| 2 | `source.query.executed` | `tool` | `{ search_parameters, provider }` |
| 3 | `source.result.normalized` | `tool` | `{ count, search_run_id, lead_ids }` |

## DB Write Matrix

| Action | Table(s) | Notes |
|---|---|---|
| Init session | `conversation_session` + `agent_conversation_sessions` + `agent_conversation_states` | Created in init flow and mirrored in agent runtime |
| User message | `conversation_message` + `agent_conversation_events` | `role=user` + `message.user.received` |
| Assistant message | `conversation_message` + `agent_conversation_events` | `role=assistant` + `message.assistant.generated` |
| State update | `conversation_session.state` + `agent_conversation_states.state_json` | Keep both in sync |
| Source query audit | `agent_source_execution_audits` | Includes provider + request payload + result count |
| Search history context | `search_runs` + `search_run_leads` (read path) | Included in `conversation/history` under `search_runs` with lead preview |

## Consistency Rules

- Event log is append-only and should never be hard-deleted during normal operation.
- Session state should be updated once per completed turn.
- Do not overwrite confirmed slots unless user intent explicitly changes.
- Keep response contract stable through `response_mapper`.

## Troubleshooting

- If user reports missing history: inspect `conversation/history` output and verify `events` and `messages` ordering.
- If provider mismatch occurs: check `provider_metadata` in response and `agent_source_execution_audits`.
- If loop-like behavior occurs: verify `clarification_turns` in state and guard behavior in `FlowStateMachine`.
- If search context is missing: verify `search_run_id` exists in source events and `search_runs` is returned in history.
