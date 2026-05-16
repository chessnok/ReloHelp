"""Unit tests for app/cache/redis.RedisCache (fakeredis-backed)."""

from __future__ import annotations

import pytest

from app.cache.redis import RedisCache


@pytest.fixture
def cache(fake_redis: RedisCache) -> RedisCache:
    return fake_redis


async def test_set_get_roundtrip(cache):
    await cache.set("k", b"v")
    assert await cache.get("k") == b"v"


async def test_set_with_ttl_and_exists(cache):
    await cache.set("k", b"v", ttl=60)
    assert await cache.exists("k") is True


async def test_delete_returns_true(cache):
    await cache.set("k", b"v")
    assert await cache.delete("k") is True
    assert await cache.exists("k") is False


async def test_delete_missing_returns_false(cache):
    assert await cache.delete("none") is False


async def test_incr_and_expire(cache):
    assert await cache.incr("c") == 1
    assert await cache.incr("c") == 2
    assert await cache.expire("c", 30) is True


async def test_close_resets_client(cache):
    await cache.close()
    assert cache._client is None
