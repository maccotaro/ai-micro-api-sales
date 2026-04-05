import json
import logging

import redis

logger = logging.getLogger(__name__)


class MessageBus:
    def __init__(self, redis_url: str, db: int = 3):
        try:
            self._redis = redis.Redis.from_url(
                redis_url, db=db, decode_responses=True
            )
            self._redis.ping()
        except Exception as e:
            logger.warning("MessageBus: Redis connection failed: %s", e)
            self._redis = None

    def publish(self, channel: str, event: dict) -> None:
        if self._redis is None:
            return
        try:
            self._redis.publish(channel, json.dumps(event))
        except Exception as e:
            logger.error("MessageBus.publish error: %s", e)
