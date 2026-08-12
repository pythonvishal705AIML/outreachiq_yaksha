"""
Lightweight in-memory cache with TTL for intent classification results.
Avoids redundant LLM calls for identical user messages within a short window.
"""
import time
import threading

_lock = threading.Lock()
_cache: dict[str, tuple[dict, float]] = {}
TTL_SECONDS = 300  # 5 minutes


def get_cached_intent(text: str) -> dict | None:
    key = text.strip().lower()
    with _lock:
        entry = _cache.get(key)
        if entry and (time.monotonic() - entry[1]) < TTL_SECONDS:
            return entry[0]
        if entry:
            del _cache[key]
    return None


def set_cached_intent(text: str, result: dict):
    key = text.strip().lower()
    with _lock:
        # Cap cache size to prevent unbounded growth
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (result, time.monotonic())
