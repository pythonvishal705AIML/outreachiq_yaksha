# Prompting and Anti-loop Controls

## Root Prompt
Use `agent_runtime/prompts.py` as the base for orchestrator policies:
- stable response contract
- deterministic routing
- loop prevention and bounded clarification

## Campaign Prompt
Use brand-manager voice prompt in campaign/email generation:
- strategic and concise
- actionable language
- context-aware outputs

## Clarification-first Campaign Behavior
- Campaign agent must ask for missing campaign essentials before generation.
- Expected essentials include goal, target audience, and tone.
- Only when clarifier status is `ready_for_generation` should campaign + email generation run.
- If clarifier returns `questions`, ask the first concrete question to keep the turn focused.

## Anti-loop Rules
- max clarification turns per topic: 2
- fallback to sensible defaults after threshold
- do not repeat same clarification consecutively
- always move turn state forward

## Prompt Maintenance
When updating prompts:
1. Keep system policies consistent with response contract.
2. Add tests for state-machine behavior if loop rules change.
3. Avoid changing output field names.
