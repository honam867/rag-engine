from __future__ import annotations

import redis.asyncio as redis

from server.app.core.config import get_settings

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return a shared Redis client for the process."""
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis.url, decode_responses=True)
    return _redis

