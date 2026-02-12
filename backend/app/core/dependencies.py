from typing import Optional
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.models.session import Session
from app.db.models.user import User
from app.db.session import get_db_session


async def get_current_user(
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Dependency to get the current authenticated user from access token."""
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token not provided",
        )

    try:
        payload = decode_token(access_token)
        user_id = UUID(payload["sub"])
        token_type = payload.get("type")

        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is inactive",
            )

        return user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from e


async def get_refresh_session(
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db_session),
) -> tuple[Session, str]:
    """Dependency to get the current refresh session from refresh token.

    Returns (session, random_part) for hash verification.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not provided",
        )

    try:
        from app.core.security import decode_refresh_token, verify_refresh_token

        payload, random_part = decode_refresh_token(refresh_token)
        jti = UUID(payload["jti"])
        token_type = payload.get("type")

        if token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        result = await db.execute(select(Session).where(Session.id == jti))
        session = result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session not found",
            )

        if session.revoked_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked",
            )

        from datetime import datetime, timezone

        if session.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has expired",
            )

        # Verify refresh token hash (replay detection)
        if not verify_refresh_token(random_part, session.refresh_token_hash):
            # Token replay detected - revoke all user sessions
            from sqlalchemy import update

            await db.execute(
                update(Session)
                .where(Session.user_id == session.user_id, Session.revoked_at.is_(None))
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await db.commit()

            from app.core.logger import logger

            logger.warning(
                f"Token replay detected for user {session.user_id}. All sessions revoked."
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token replay detected. All sessions have been revoked.",
            )

        return session, random_part

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate refresh token",
        ) from e


def get_csrf_token(request: Request) -> Optional[str]:
    """Get CSRF token from request header."""
    return request.headers.get("X-CSRF-Token")
