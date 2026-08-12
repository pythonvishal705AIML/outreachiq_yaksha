"""
Streaming extension for LLMClient.
Usage: for chunk in stream_completion(messages): yield chunk
"""
import logging
from api.clients.llm_client import _get_shared_client

logger = logging.getLogger(__name__)


def stream_completion(messages, model="gpt-4o-mini", temperature=0.7, max_tokens=None):  # gpt-4o-mini: fast streaming
    """
    Generator that yields text chunks as they arrive from OpenAI.
    Drop-in replacement for LLMClient.get_completion() in streaming contexts.
    """
    client = _get_shared_client()
    params = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if max_tokens:
        params["max_completion_tokens"] = max_tokens

    try:
        response = client.chat.completions.create(**params)
        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
    except Exception as e:
        logger.error("stream_completion error: %s", e, exc_info=True)
        raise
