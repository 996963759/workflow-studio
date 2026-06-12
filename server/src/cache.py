import json
import logging
from typing import Any

from .config import REDIS_SOCKET_TIMEOUT_SECONDS, REDIS_URL

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - dependency is optional when Redis is disabled.
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):
        pass


logger = logging.getLogger("workflow_studio.cache")


class JsonCache:
    def __init__(
        self,
        redis_url: str = REDIS_URL,
        namespace: str = "workflow-studio",
        socket_timeout_seconds: float = REDIS_SOCKET_TIMEOUT_SECONDS,
    ) -> None:
        self.redis_url = redis_url.strip()
        self.namespace = namespace.strip(":")
        self.socket_timeout_seconds = socket_timeout_seconds
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.redis_url)

    def _get_client(self):
        if not self.enabled:
            return None
        if Redis is None:
            logger.warning("redis package is not installed; cache is disabled")
            return None
        if self._client is None:
            self._client = Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=self.socket_timeout_seconds,
                socket_connect_timeout=self.socket_timeout_seconds,
            )
        return self._client

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get_json(self, key: str) -> Any | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            value = client.get(self._key(key))
            if value is None:
                return None
            return json.loads(value)
        except (RedisError, json.JSONDecodeError, TypeError):
            logger.warning("cache read failed key=%s", key, exc_info=True)
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        client = self._get_client()
        if client is None:
            return
        try:
            client.setex(
                self._key(key),
                ttl_seconds,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            )
        except (RedisError, TypeError, ValueError):
            logger.warning("cache write failed key=%s", key, exc_info=True)

    def delete(self, key: str) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            client.delete(self._key(key))
        except RedisError:
            logger.warning("cache delete failed key=%s", key, exc_info=True)


default_cache = JsonCache()
