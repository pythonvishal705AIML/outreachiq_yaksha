import json
import logging
import re
from typing import List, Dict
from ..clients.llm_client import LLMClient
from ..prompts import INTENT_CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)


def _strip_json_markdown(text: str) -> str:
    """
    Remove ```json ... ``` wrappers if present so json.loads works.
    """
    if not text or not isinstance(text, str):
        return text or ""
    cleaned = text.strip()
    # Remove opening ```json or ```
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
    # Remove closing ```
    cleaned = re.sub(r'\n?\s*```\s*$', '', cleaned)
    return cleaned.strip()


class IntentClassifier:
    """
    A class that encapsulates intent classification logic using LLMClient.
    """

    # ---- Keyword patterns for fallback intent detection ----
    LEAD_SEARCH_KEYWORDS = [
        "find", "search", "look for", "looking for", "get me", "find me",
        "show me", "fetch", "who are", "list of",
        "cto", "ceo", "cfo", "coo", "cmo", "vp", "director", "manager",
        "founder", "head of", "leads", "people", "contacts",
        "companies", "organizations", "startups", "enterprises",
        "in healthcare", "in saas", "in fintech", "in tech",
        "at google", "at microsoft", "at amazon",
        "san francisco", "new york", "united states", "india", "london",
    ]

    CAMPAIGN_KEYWORDS = [
        "campaign", "outreach", "email sequence", "follow-up",
        "generate email", "create campaign", "build campaign",
        "sales outreach", "cold email", "drip",
    ]

    CHIT_CHAT_KEYWORDS = [
        "hello", "good morning", "good afternoon",
        "how are you", "what can you do", "help me", "what is this",
        "how does this work", "thanks", "thank you", "bye",
    ]
    # Add these 3 new class-level constants after line 56:

    LEAD_ANCHOR_KEYWORDS = [
        "cto", "ceo", "cfo", "coo", "cmo",
        "vp of", "head of", "founders",
        "prospects", "contacts", "leads",
    ]

    CAMPAIGN_ANCHOR_KEYWORDS = [
        "campaign", "outreach", "cold email",
        "email sequence", "drip",
    ]

    CHIT_CHAT_ANCHOR_KEYWORDS = [
        "hello", "hi", "hey",
        "good morning", "good afternoon",
        "thanks", "thank you", "bye",
    ]
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0):  # gpt-4o-mini: faster intent classification
        self.model = model
        self.temperature = temperature
        self.llm_client = LLMClient()
        self.base_prompt = INTENT_CLASSIFICATION_PROMPT

    # def classify(self, history: List[Dict[str, str]]) -> Dict:
    #     """
    #     Sends conversation history to the LLM and returns the parsed JSON intent.
    #     Falls back to keyword-based detection if LLM fails or returns empty.
    #     """
    #
    #     logger.debug(f"Classify Intent. History length: {len(history)}")
    #
    #     # Extract latest user message for fallback
    #     latest_user_text = ""
    #     for msg in reversed(history):
    #         if msg.get("role") == "user":
    #             latest_user_text = msg.get("content", "")
    #             break
    #
    #     # --- Try LLM classification first ---
    #     messages = [
    #         {"role": "system", "content": self.base_prompt},
    #         {"role": "user", "content": json.dumps(history)}
    #     ]
    #
    #     try:
    #         content = self.llm_client.get_completion(
    #             messages=messages,
    #             model=self.model,
    #             temperature=self.temperature,
    #             max_tokens=200,
    #             json_mode=True
    #         )
    #
    #         logger.info(f"Intent Classification Raw Response: '{content}'")
    #
    #         if content and content.strip():
    #             result = self._parse_response(content)
    #             if result.get("general_intent") != "unknown":
    #                 return result
    #             logger.warning("LLM returned parseable response but intent was 'unknown', trying keyword fallback")
    #         else:
    #             logger.warning("LLM returned empty response, falling back to keyword detection")
    #
    #     except Exception as e:
    #         logger.error(f"Intent Classification LLM Error: {e}", exc_info=True)

        # --- Keyword-based fallback ---
        # fallback_result = self._keyword_fallback(latest_user_text)
        # logger.info(f"Intent Keyword Fallback Result: {fallback_result}")
        # return fallback_result
    def classify(self, history: List[Dict[str, str]]) -> Dict:
        """
        OPTIMIZED: Keywords FIRST (instant, ~0ms), LLM only if ambiguous.
        """
        logger.debug(f"Classify Intent. History length: {len(history)}")

        latest_user_text = ""
        for msg in reversed(history):
            if msg.get("role") == "user":
                latest_user_text = msg.get("content", "")
                break

        # STEP 1: Keywords first (instant)
        keyword_result, confidence = self._keyword_classify_with_confidence(latest_user_text)

        if confidence == "high":
            logger.info(f"Intent via KEYWORDS: {keyword_result['general_intent']} (skipped LLM)")
            return keyword_result

        # STEP 2: LLM only if keywords can't decide
        logger.info(f"Keywords inconclusive (confidence={confidence}). Calling LLM...")
        messages = [
            {"role": "system", "content": self.base_prompt},
            {"role": "user", "content": json.dumps(history)}
        ]

        try:
            content = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=200,
                json_mode=True
            )

            if content and content.strip():
                result = self._parse_response(content)
                if result.get("general_intent") != "unknown":
                    return result

        except Exception as e:
            logger.error(f"Intent Classification LLM Error: {e}", exc_info=True)

        # STEP 3: Use keyword result even if low confidence
        if keyword_result.get("general_intent") != "unknown":
            return keyword_result

        return {"general_intent": "unknown", "entities": {}}

    def _keyword_classify_with_confidence(self, text: str) -> tuple:
        if not text:
            return {"general_intent": "unknown", "entities": {}}, "none"

        text_lower = text.lower().strip()

        # ── NEW: Anchor check — single unambiguous word skips LLM entirely ──
        # Use word-boundary regex to avoid substring false-positives (e.g. "hi" inside "architects")
        def _word_match(keywords, text):
            return any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in keywords)

        lead_anchor = _word_match(self.LEAD_ANCHOR_KEYWORDS, text_lower)
        campaign_anchor = _word_match(self.CAMPAIGN_ANCHOR_KEYWORDS, text_lower)
        chit_chat_anchor = _word_match(self.CHIT_CHAT_ANCHOR_KEYWORDS, text_lower)

        anchor_hits = sum([lead_anchor, campaign_anchor, chit_chat_anchor])

        # Only fire if exactly ONE intent matches (avoids "create campaign for leads" ambiguity)
        if anchor_hits == 1:
            if lead_anchor:
                return {"general_intent": "lead_search", "entities": {}}, "high"
            if campaign_anchor:
                return {"general_intent": "create_campaign", "entities": {}}, "high"
            if chit_chat_anchor:
                return {"general_intent": "chit_chat", "entities": {}}, "high"
        # ── END NEW ──

        # ── UNCHANGED from line 117 onward ──
        lead_score = sum(1 for kw in self.LEAD_SEARCH_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', text_lower))
        campaign_score = sum(1 for kw in self.CAMPAIGN_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', text_lower))
        chit_chat_score = sum(1 for kw in self.CHIT_CHAT_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', text_lower))

        max_score = max(lead_score, campaign_score, chit_chat_score)
        scores = sorted([lead_score, campaign_score, chit_chat_score], reverse=True)

        if max_score == 0:
            return {"general_intent": "unknown", "entities": {}}, "none"

        if lead_score >= campaign_score and lead_score >= chit_chat_score:
            intent = "lead_search"
        elif campaign_score >= lead_score and campaign_score >= chit_chat_score:
            intent = "create_campaign"
        else:
            intent = "chit_chat"

        result = {"general_intent": intent, "entities": {}}

        if max_score >= 2 and (scores[0] - scores[1]) >= 1:
            return result, "high"

        return result, "low"
   #hi
    def _keyword_fallback(self, text: str) -> Dict:
        """
        Simple keyword-based intent detection as fallback when LLM fails.
        """
        if not text:
            return {"general_intent": "unknown", "entities": {}}
        
        text_lower = text.lower().strip()
        
        # Score each intent by how many keywords match
        lead_score = sum(1 for kw in self.LEAD_SEARCH_KEYWORDS if kw in text_lower)
        campaign_score = sum(1 for kw in self.CAMPAIGN_KEYWORDS if kw in text_lower)
        chit_chat_score = sum(1 for kw in self.CHIT_CHAT_KEYWORDS if kw in text_lower)
        
        logger.debug(f"Keyword scores - lead: {lead_score}, campaign: {campaign_score}, chit_chat: {chit_chat_score}")
        
        # Pick the highest scoring intent (minimum 1 match required)
        max_score = max(lead_score, campaign_score, chit_chat_score)
        
        if max_score == 0:
            return {"general_intent": "unknown", "entities": {}}
        
        if lead_score >= campaign_score and lead_score >= chit_chat_score:
            return {"general_intent": "lead_search", "entities": {}}
        if campaign_score >= lead_score and campaign_score >= chit_chat_score:
            return {"general_intent": "create_campaign", "entities": {}}
        
        return {"general_intent": "chit_chat", "entities": {}}

    def _parse_response(self, text: str) -> Dict:
        """
        Parse JSON from the LLM response, being tolerant of markdown fences
        and other common formatting issues.
        """
        if not text:
            return {"general_intent": "unknown", "entities": {}}

        # Step 1: Strip markdown fences
        raw = _strip_json_markdown(text)

        # Step 2: Try direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Step 3: Try to find JSON object in the text using regex
        try:
            match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except json.JSONDecodeError:
            pass

        # Step 4: Keyword fallback - check if text mentions known intents
        text_lower = text.lower()
        if "lead_search" in text_lower:
            return {"general_intent": "lead_search", "entities": {}}
        if "create_campaign" in text_lower:
            return {"general_intent": "create_campaign", "entities": {}}
        if "chit_chat" in text_lower:
            return {"general_intent": "chit_chat", "entities": {}}

        logger.warning(f"Failed to parse Intent JSON: {raw[:200]}...")
        return {"general_intent": "unknown", "entities": {}}