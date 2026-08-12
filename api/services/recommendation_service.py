
import json
import logging
import re
import hashlib                                    # ADDED
from django.forms.models import model_to_dict
from django.core.cache import cache               # ADDED
from api.clients.llm_client import LLMClient
from api.models import BusinessProfile
from api.prompts import RECOMMENDATION_PROMPT

logger = logging.getLogger(__name__)
CACHE_TTL = 60 * 60 * 24                         # ADDED: 24 hour cache


def _strip_json_markdown(text: str) -> str:
    """Remove ```json and ``` wrappers if present so json.loads works."""
    if not text or not isinstance(text, str):
        return text or ""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
    if text.endswith("```"):
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


class RecommendationService:
    def __init__(self):
        self.llm_client = LLMClient()
        self.model = "gpt-4o-mini"
    def generate_suggested_prompts(self, account_id: str) -> dict:
        """
        Generates 4 personalized lead search prompts based on the business profile.
        """
        # Fast cache check before hitting the DB
        simple_cache_key = f"icp_prompts:{account_id}"
        cached = cache.get(simple_cache_key)
        if cached:
            return cached

        # 1. Fetch Profile
        try:
            profile = BusinessProfile.objects.get(account_id=account_id)
        except BusinessProfile.DoesNotExist:
            raise ValueError(f"Business Profile not found for account_id: {account_id}")

        profile_dict = model_to_dict(profile)
        cache_key = f"icp_prompts:{account_id}:{hashlib.md5(json.dumps(profile_dict, sort_keys=True, default=str).encode()).hexdigest()}"
        cached = cache.get(cache_key)
        if cached:
            cache.set(simple_cache_key, cached, CACHE_TTL)
            return cached

        # 2. Prepare Context from Profile (use dict so prompt gets readable text)
        profile_str = json.dumps(profile_dict, indent=2, default=str)
        prompt = RECOMMENDATION_PROMPT.format(
            business_profile=profile_str
        )

        messages = [
            {"role": "system", "content": prompt}
        ]

        # 3. Call LLM
        response_text = self.llm_client.get_completion(
            messages=messages,
            model=self.model,
            temperature=0.7, # Allow some creativity
            json_mode=True
        )

        # 4. Parse Response (strip markdown code blocks; accept "prompts" or legacy key)
        raw = _strip_json_markdown(response_text)
        try:
            data = json.loads(raw)
            # Normalize
        except json.JSONDecodeError as e:
            logger.warning("Recommendation Service: LLM response is not valid JSON: %s", e)
            return {"prompts": []}

        prompts_list = data.get("prompts")
        if prompts_list is None:
            # Legacy: prompt used to say "prompts with each 10 words"
            prompts_list = data.get("prompts with each 10 words")
        if not isinstance(prompts_list, list):
            logger.warning("Recommendation Service: Invalid LLM response format (missing or non-list 'prompts').")
            return {"prompts": []}

        # Ensure we return exactly 4 strings
        out = []
        for i, p in enumerate(prompts_list):
            if i >= 4:
                break
            if isinstance(p, str):
                out.append(p.strip())
            elif p is not None:
                out.append(str(p).strip())
        result = {"prompts": out}
        cache.set(cache_key, result, CACHE_TTL)
        cache.set(simple_cache_key, result, CACHE_TTL)
        return result
