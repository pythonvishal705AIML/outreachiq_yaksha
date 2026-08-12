class FlowStateMachine:
    MAX_CLARIFICATION_TURNS = 2

    @staticmethod
    def can_ask_clarification(state: dict) -> bool:
        return int((state or {}).get("clarification_turns", 0)) < FlowStateMachine.MAX_CLARIFICATION_TURNS

    @staticmethod
    def increment_clarification(state: dict) -> dict:
        updated = dict(state or {})
        updated["clarification_turns"] = int(updated.get("clarification_turns", 0)) + 1
        return updated
