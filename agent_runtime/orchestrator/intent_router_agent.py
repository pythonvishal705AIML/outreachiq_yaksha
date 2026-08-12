import logging
from api.services.intent_classifier import IntentClassifier
from agent_runtime.prompts import ROOT_ORCHESTRATOR_PROMPT
from agent_runtime.orchestrator.intent_cache import get_cached_intent, set_cached_intent

logger = logging.getLogger(__name__)

# Token-heavy keys to strip from history before sending to intent LLM
_STRIP_KEYS = {"metadata", "parameters", "lead_ids", "search_run_id", "imageUrl", "photos"}


def _compact_history(history: list[dict]) -> list[dict]:
    """Strip token-heavy fields from history before classification."""
    compact = []
    for msg in history[-6:]:  # Only last 6 msgs for intent classification (not full 10)
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 500:
            content = content[:500]  # Truncate very long messages
        compact.append({"role": msg["role"], "content": content})
    return compact


class IntentRouterAgent:
    def __init__(self):
        self.classifier = IntentClassifier()
        self.classifier.base_prompt = ROOT_ORCHESTRATOR_PROMPT

    def route(self, history: list[dict]) -> str:
        # Extract latest user text
        latest = ""
        for msg in reversed(history):
            if msg.get("role") == "user":
                latest = msg.get("content", "")
                break

        # Check cache first — same text = same intent, skip LLM
        cached = get_cached_intent(latest)
        if cached:
            logger.debug("Intent cache HIT: %s", cached.get("general_intent"))
            return cached.get("general_intent") or "unknown"

        compact = _compact_history(history)
        classification = self.classifier.classify(compact)
        set_cached_intent(latest, classification)
        return classification.get("general_intent") or "unknown"
