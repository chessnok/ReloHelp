from datetime import timedelta
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from app.core.config import settings


async def check_rate_limit(
    redis_client: Any,
    key: str,
    max_requests: int,
    window_seconds: int,
) -> bool:
    """
    Check if a request should be rate limited.
    Returns True if allowed, False if rate limited.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return True

    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, window_seconds)

    return current <= max_requests


async def get_rate_limit_key(request: Request, identifier: str) -> str:
    """Generate a rate limit key from request."""
    client_ip = request.client.host if request.client else "unknown"
    return f"rate_limit:{identifier}:{client_ip}"


async def check_login_rate_limit(
    redis_client: Any, request: Request, email: str
) -> None:
    """Check rate limit for login attempts."""
    key = await get_rate_limit_key(request, f"login:{email}")
    allowed = await check_rate_limit(
        redis_client,
        key,
        settings.RATE_LIMIT_LOGIN_ATTEMPTS,
        settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
