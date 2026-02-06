"""Fetch AI model settings from api-admin internal API.

Uses GET /internal/model-settings with X-Internal-Secret auth.
TTL-based cache (5 minutes) with hardcoded fallback defaults.
"""
import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_cached_settings: Optional[Dict[str, Any]] = None
_cache_timestamp: float = 0.0
_CACHE_TTL_SECONDS: float = 300.0  # 5 minutes

# Hardcoded fallback defaults (used only when internal API is unreachable)
_DEFAULTS: Dict[str, Any] = {
    "embedding_model": "bge-m3:567m",
    "embedding_dimension": 1024,
    "chat_model": "qwen3:8b",
    "tool_model": "llama3.1:8b",
    "vlm_model": "qwen2.5vl:7b",
    "reranker_model": "BAAI/bge-reranker-base",
    "distance_metric": "cosine",
}


def _fetch_from_api() -> Optional[Dict[str, Any]]:
    """Fetch model settings from api-admin internal API."""
    url = f"{settings.admin_internal_url}/internal/model-settings"
    try:
        resp = httpx.get(
            url,
            headers={"X-Internal-Secret": settings.internal_api_secret},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch model settings from {url}: {e}")
        return None


def get_model_settings() -> Dict[str, Any]:
    """Get model settings with TTL cache (5 min)."""
    global _cached_settings, _cache_timestamp
    now = time.monotonic()
    if _cached_settings is not None and (now - _cache_timestamp) < _CACHE_TTL_SECONDS:
        return _cached_settings
    result = _fetch_from_api()
    if result:
        _cached_settings = result
        _cache_timestamp = now
        logger.info("Loaded model settings from api-admin internal API")
        return _cached_settings
    # Return stale cache if available
    if _cached_settings is not None:
        logger.info("Using stale cached settings")
        return _cached_settings
    logger.warning("Using hardcoded fallback defaults for model settings")
    return _DEFAULTS


def _get(key: str) -> Any:
    """Get a single setting value with fallback to defaults."""
    return get_model_settings().get(key, _DEFAULTS.get(key))


def get_chat_model() -> str:
    """Get chat/LLM model name."""
    return _get("chat_model")


def get_embedding_model() -> str:
    """Get embedding model name."""
    return _get("embedding_model")


def reset_cache():
    """Clear the cached settings."""
    global _cached_settings, _cache_timestamp
    _cached_settings = None
    _cache_timestamp = 0.0
