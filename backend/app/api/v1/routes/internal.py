"""Internal service-to-service endpoints. Protected by INTERNAL_API_TOKEN header.

These endpoints are intended for trusted internal callers only (e.g. the MCP
server) and must NOT be exposed to public clients.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.db.models.memory import Memory
from app.db.models.user import User
from app.db.session import get_db_session
from app.services.memory import get_memory_service

_MEMORY_LIST_CAP = 50
_VALID_MEMORY_KINDS = frozenset({"fact", "preference", "event", "summary"})

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


@router.get(
    "/users/{user_id}/memories",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_require_internal_token)],
)
async def get_user_memories_internal(
    user_id: str,
    query: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    top_k: int = Query(default=10, ge=1, le=_MEMORY_LIST_CAP),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return per-user memories.

    Modes:
      - `query` set → semantic search via MemoryService (cosine, gated by
        MEMORY_MIN_SIMILARITY); `kind` is ignored.
      - `query` empty + `kind` set → all memories of that kind, newest first.
      - `query` empty + `kind` empty → all memories for the user, newest first.

    `top_k` is clamped to [1, _MEMORY_LIST_CAP].
    """
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )
    if kind is not None and kind not in _VALID_MEMORY_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid kind; expected one of {sorted(_VALID_MEMORY_KINDS)}",
        )

    if query and query.strip():
        try:
            hits = await get_memory_service().search(
                db, uid, query.strip(), top_k=top_k
            )
        except Exception as exc:  # noqa: BLE001 — boundary catch
            logger.warning("Memory semantic search failed: %s", exc)
            return {"memories": [], "error": "Memory search failed"}
        return {
            "memories": [
                {
                    "id": str(h.id),
                    "kind": h.kind,
                    "content": h.content,
                    "similarity": h.similarity,
                    "metadata": h.metadata,
                }
                for h in hits
            ]
        }

    stmt = select(Memory).where(Memory.user_id == uid)
    if kind is not None:
        stmt = stmt.where(Memory.kind == kind)
    stmt = stmt.order_by(Memory.created_at.desc()).limit(top_k)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "memories": [
            {
                "id": str(m.id),
                "kind": m.kind,
                "content": m.content,
                "metadata": m.meta or {},
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]
    }
