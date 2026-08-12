import json
import logging
from ..clients.llm_client import LLMClient
from ..prompts import LEAD_EXTRACTION_PROMPT
from ..normalization.filter_normalizer import get_normalizer
logger = logging.getLogger(__name__)

class LeadParameterExtractor:
    """
    Service to extract structured lead search parameters from a business description using LLM.
    """

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0):  # temperature=0 → deterministic JSON, no random sampling
        self.model = model
        self.temperature = temperature
        self.llm_client = LLMClient()
        self.filter_normalizer = get_normalizer()
    def extract(self, business_data: dict, current_state: dict = None, user_query: str = None, history: list = None, post_process: bool = False) -> dict:
        """
        Extracts lead search parameters.
        """
        
        system_prompt = LEAD_EXTRACTION_PROMPT

        # Prepare context for LLM
        # logger.debug(f"Extract Params Current State: {json.dumps(current_state)}")
        state_str = json.dumps(current_state or {}, indent=2)
        profile_str = json.dumps(business_data or {}, indent=2)
        
        # Format history string
        history_str = ""
        if history:
            # Simple format: "User: ... \n Assistant: ..."
            history_str = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in history])
        user_message = (
            f"Business Profile: {profile_str}\n"
            f"Current State: {state_str}\n"
            f"Conversation History (Last 5): {history_str}\n"
            f"Latest Input: {user_query or 'N/A'}"
        )

        try:
            content = self.llm_client.get_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                model=self.model,
                temperature=self.temperature,
                json_mode=True
            )
            
            # Parse JSON
            raw_data = json.loads(content)

            # Normalize extracted parameters to the canonical filter taxonomy only.
            # Preserve passthrough metadata fields and any new prompt parameters
            # that are not part of the normalizer taxonomy.
            raw_params = raw_data.get("parameters", {})
            normalized_params = self.filter_normalizer.normalize(raw_params)
            
            for key, val in raw_params.items():
                if key not in normalized_params:
                    normalized_params[key] = val
                    
            raw_data["parameters"] = normalized_params
            
            # Post-Process (Normalize & add Confidence) IF requested
            if post_process:
                return self._post_process(raw_data)
            
            return raw_data

        except Exception as e:
            logger.error(f"Error in LeadParameterExtractor: {e}", exc_info=True)
            return {
                "error": str(e),
                "status": "ERROR"
            }

    def _post_process(self, data: dict) -> dict:
        """
        Validates fields, normalizes data, and adds confidence placeholders.
        """
        params = data.get("parameters", {})
        
        # 1. Normalize Titles
        # We skip .title() to avoid breaking acronyms like "CEO" returned explicitly by prompt.

        # 2. Normalize Seniority (Lowercase)
        if "person_seniorities" in params:
             params["person_seniorities"] = [s.lower() for s in params["person_seniorities"]]

        # 3. Add Confidence Scores (Mocking logic for now)
        confidence = {
            "overall": 0.85 if params else 0.5,
            "roles": 0.9 if params.get("person_titles") else 0.0,
            "locations": 0.9 if params.get("person_locations") or params.get("organization_locations") else 0.0
        }
        
        data["confidence"] = confidence
        
        # 4. Ensure Status
        if not data.get("status"):
            data["status"] = "COMPLETE" if params else "MISSING_INFO"
            
        return data