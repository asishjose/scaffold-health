import redis

from app.core.config import settings

_redis_client: "redis.Redis | None" = None

# Fail fast rather than fail open-but-slow: redis-py's default connect
# timeout is None, which blocks on the OS-level TCP timeout (can be tens
# of seconds) if Redis is unreachable. Callers that treat a RedisError as
# a cache miss depend on failures surfacing quickly.
_SOCKET_TIMEOUT_SECONDS = 0.2


def get_redis_client() -> "redis.Redis":
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    _redis_client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=_SOCKET_TIMEOUT_SECONDS,
        socket_timeout=_SOCKET_TIMEOUT_SECONDS,
    )
    return _redis_client
