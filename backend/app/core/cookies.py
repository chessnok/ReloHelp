from fastapi import Response

from app.core.config import settings


def set_access_token_cookie(response: Response, token: str) -> None:
    """Set access token as httpOnly Secure cookie."""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAME_SITE.lower(),
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def set_refresh_token_cookie(response: Response, token: str) -> None:
    """Set refresh token as httpOnly Secure cookie."""
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAME_SITE.lower(),
        domain=settings.COOKIE_DOMAIN,
        path="/auth/token/refresh",
    )


def set_csrf_token_cookie(response: Response, token: str) -> None:
    """Set CSRF token as cookie."""
    response.set_cookie(
        key="csrf_token",
        value=token,
        httponly=False,  # CSRF token must be accessible to JavaScript
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAME_SITE.lower(),
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def delete_auth_cookies(response: Response) -> None:
    """Delete all authentication cookies."""
    response.delete_cookie(
        key="access_token",
        path="/",
        domain=settings.COOKIE_DOMAIN,
    )
    response.delete_cookie(
        key="refresh_token",
        path="/auth/token/refresh",
        domain=settings.COOKIE_DOMAIN,
    )
    response.delete_cookie(
        key="csrf_token",
        path="/",
        domain=settings.COOKIE_DOMAIN,
    )
