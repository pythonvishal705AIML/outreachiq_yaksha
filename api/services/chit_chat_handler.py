import logging
from ..clients.llm_client import LLMClient
from ..prompts import CHIT_CHAT_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

class BrandChitChatHandler:
    """
    Brand-aware chit-chat handler using LLM.
    """

    def __init__(self, brand_name: str, brand_tone: str = "friendly"):
        self.brand_name = brand_name
        
        # Handle if tone is a list (e.g., ["Professional", "Clear"])
        if isinstance(brand_tone, list):
             self.brand_tone = ", ".join(brand_tone) if brand_tone else "friendly"
        else:
             self.brand_tone = brand_tone or "friendly"
             
        self.llm_client = LLMClient()

    def respond(self, user_text: str, history: list = None) -> str:
        """
        Generates a contextual, brand-aware response using LLM.
        """
        system_prompt = CHIT_CHAT_PROMPT_TEMPLATE.format(
            brand_name=self.brand_name,
            brand_tone=self.brand_tone
        )

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        # print("History:",history)
        if history:
            messages.extend(history)
        else:
            messages.append({"role": "user", "content": user_text})

        try:
            return self.llm_client.get_completion(
                messages=messages,
                model="gpt-4o-mini",   # ← was gpt-5-mini
                temperature=0.7,
                max_tokens=100
            )

        except Exception as e:
            # Fallback if API fails
            logger.error(f"ChitChat LLM Error: {e}", exc_info=True)
            return f"Hello! I'm here to help you with {self.brand_name}."