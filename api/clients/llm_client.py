import os
import json
import logging
import openai
from dotenv import load_dotenv
from django.conf import settings

# Ensure env vars are loaded if not already handled by Django settings
load_dotenv()

logger = logging.getLogger(__name__)
_shared_client = None


def _get_shared_client():
    global _shared_client
    if _shared_client is None:
        api_key = (
                os.getenv("OPENAI_API_KEY")
                or getattr(settings, "OPENAI_API_KEY", None)
        )
        _shared_client = openai.OpenAI(
            api_key=api_key,
            timeout=90.0,  # don't hang forever
            max_retries=2,  # retry once on transient errors (rate limits, timeouts)
        )
    return _shared_client


class LLMClient:
    """
    Wrapper for OpenAI API interactions.
    """

    # def __init__(self, api_key=None):
    #     self.api_key = api_key or os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    #     if self.api_key:
    #         openai.api_key = self.api_key
    #
    #     self.client = openai
    # NEW (replace with)
    def __init__(self, api_key=None):
        self.client = _get_shared_client()

    def get_completion(self, messages, model="gpt-4o-mini", temperature=0.7, max_tokens=None, json_mode=False):  # global default: fast + stable
        """
        Get a completion from the LLM.
        """
        try:
            logger.debug(f"LLM Request: Model={model}, Temp={temperature}, JsonMode={json_mode}")

            response_format = {"type": "json_object"} if json_mode else None

            # Using implicit logic for max_tokens vs max_completion_tokens if needed,
            # but standardizing on passing what is provided.
            # Assuming the library handles None or we pass it if strictly provided.

            param_max_tokens = max_tokens

            # Explicitly call create without **kwargs
            # response = self.client.chat.completions.create(
            #     model=model,
            #     messages=messages
            # )
            params = {
                "model": model,
                "messages": messages,

            }
            #
            # if param_max_tokens:
            #     params["max_tokens"] = param_max_tokens
            if param_max_tokens:
                params["max_completion_tokens"] = param_max_tokens

            if response_format:
                params["response_format"] = response_format

            response = self.client.chat.completions.create(**params)
            raw_content = response.choices[0].message.content
            if raw_content is None:
                logger.warning(
                    f"LLMClient: Got None content. Finish reason: {response.choices[0].finish_reason}, Model: {model}")
                return ""

            content = raw_content.strip()
            logger.debug(f"LLM Response (first 200 chars): {content[:200]}")
            return content

        except Exception as e:
            logger.error(f"LLMClient Error: {e}", exc_info=True)
            raise e

    def get_embedding(self, text, model="text-embedding-3-small"):
        """
        Generates embedding for the given text.
        """
        try:
            # Clean newlines which can negatively affect performance
            text = text.replace("\n", " ")

            response = self.client.embeddings.create(
                input=[text],
                model=model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding Failed: {e}")
            raise e

