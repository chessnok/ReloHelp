"""Internal service-to-service endpoints. Protected by INTERNAL_API_TOKEN header.

These endpoints are intended for trusted internal callers only (e.g. the MCP
server) and must NOT be exposed to public clients.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db_session

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


def _require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    expected = settings.INTERNAL_API_TOKEN
    if not expected or x_internal_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal token",
        )


@router.get(
    "/users/{user_id}/email",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_require_internal_token)],
)
async def get_user_email_internal(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return the email of the given user. Internal use only."""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {"email": user.email or ""}
