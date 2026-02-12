"""
Module for working with Redis cache.
"""

from typing import Any, Optional

from redis.asyncio import Redis

from app.core.config import settings


class RedisCache:
    """A simple wrapper around Redis for cache operations."""

    def __init__(self):
        self.host = settings.REDIS_HOST
        self.port = settings.REDIS_PORT
        self.db = settings.REDIS_DB
        self.password = settings.REDIS_PASSWORD

        self._client: Optional[Redis] = None

    async def connect(self) -> Redis:
        """Create a Redis client if not already connected."""
        if self._client is None:
            self._client = Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
            )
        return self._client

    async def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> None:
        """Set a value with optional TTL (in seconds)."""
        client = await self.connect()
        await client.set(key, value, ex=ttl)

    async def get(self, key: str) -> Optional[bytes]:
        """Fetch a value from Redis."""
        client = await self.connect()
        return await client.get(key)

    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        client = await self.connect()
        return (await client.delete(key)) == 1

    async def exists(self, key: str) -> bool:
        """Check whether a key exists in Redis."""
        client = await self.connect()
        return (await client.exists(key)) == 1

    async def incr(self, key: str) -> int:
        """Increment a key in Redis."""
        client = await self.connect()
        return await client.incr(key)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set a timeout on key."""
        client = await self.connect()
        return await client.expire(key, seconds)

    async def close(self):
        """Close the Redis connection if open."""
        if self._client:
            await self._client.close()
            self._client = None


# Global singleton
_redis_instance: Optional[RedisCache] = None


async def get_redis_client() -> RedisCache:
    """FastAPI dependency that returns a singleton RedisCache instance."""
    global _redis_instance
    if _redis_instance is None:
        _redis_instance = RedisCache()
        await _redis_instance.connect()
    return _redis_instance
