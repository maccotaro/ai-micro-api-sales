import json
import logging
from typing import Any, Optional

import redis

logger = logging.getLogger(__name__)

_TTL_DEFAULTS = {
    "sm:agent:": 1800,
    "sm:pipeline:": 7200,
    "sm:health:": 3600,
    "sm:cache:": 3600,
}


class SharedMemory:
    def __init__(self, redis_url: str, db: int = 3):
        try:
            self._redis = redis.Redis.from_url(
                redis_url, db=db, decode_responses=True
            )
            self._redis.ping()
        except Exception as e:
            logger.warning("SharedMemory: Redis connection failed: %s", e)
            self._redis = None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if self._redis is None:
            return
        try:
            if ttl is None:
                ttl = next(
                    (v for k, v in _TTL_DEFAULTS.items() if key.startswith(k)),
                    1800,
                )
            self._redis.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.error("SharedMemory.set error: %s", e)

    def get(self, key: str) -> Optional[Any]:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as e:
            logger.error("SharedMemory.get error: %s", e)
            return None

    def delete(self, key: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.delete(key)
        except Exception as e:
            logger.error("SharedMemory.delete error: %s", e)

    def delete_pattern(self, pattern: str) -> int:
        if self._redis is None:
            return 0
        try:
            count = 0
            for key in self._redis.scan_iter(match=pattern, count=100):
                self._redis.delete(key)
                count += 1
            return count
        except Exception as e:
            logger.error("SharedMemory.delete_pattern error: %s", e)
            return 0
