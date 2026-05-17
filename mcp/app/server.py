"""FastMCP server exposing tools for the AI agent.

Tools do NOT touch the database directly. They talk to the backend over HTTP
using a shared INTERNAL_API_TOKEN.
"""

import logging
from uuid import UUID

import httpx
from fastmcp import FastMCP

from app import rag
from app.config import settings

logger = logging.getLogger("app.server")

mcp = FastMCP("Relohelp MCP Server")


def _internal_headers() -> dict[str, str]:
    if not settings.INTERNAL_API_TOKEN:
        return {}
    return {"X-Internal-Token": settings.INTERNAL_API_TOKEN}


@mcp.tool
async def get_user_email(user_id: str) -> dict:
    """Returns the authenticated user's email.

    Args:
        user_id: The UUID of the user whose email to retrieve.
    """
    try:
        UUID(user_id)
    except ValueError:
        return {"email": "", "error": "Invalid user_id format"}

    url = f"{settings.BACKEND_URL.rstrip('/')}/api/v1/internal/users/{user_id}/email"
    try:
        async with httpx.AsyncClient(
            timeout=settings.REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(url, headers=_internal_headers())
    except httpx.HTTPError as exc:
        return {"email": "", "error": f"Backend unreachable: {exc}"}

    if response.status_code == 404:
        return {"email": "", "error": "User not found"}
    if response.status_code == 401:
        return {"email": "", "error": "Unauthorized (internal token invalid)"}
    if response.status_code >= 400:
        return {"email": "", "error": f"Backend error: {response.status_code}"}

    try:
        data = response.json()
    except ValueError:
        return {"email": "", "error": "Invalid backend response"}

    return {"email": data.get("email", "")}


@mcp.tool
async def search_telegram_chats(query: str, k: int = 5) -> dict:
    """Retrieves relevant snippets from indexed Telegram relocation/visa chats.

    Use this when the user asks about real-world relocation, visa, residence permit,
    legalization, or other migration questions where on-the-ground community advice
    helps. Each hit includes `chat_id` and `date_min`/`date_max` for attribution —
    cite these in your reply.

    Args:
        query: Natural-language question (any language; Russian or English work).
        k: Number of hits to return (1..20).

    Returns:
        {"hits": [{doc_id, distance, chat_id, kind, n_msgs, date_min, date_max, snippet}, ...]}
        or {"hits": [], "error": "..."} if RAG is disabled / unavailable.
    """
    if not settings.RAG_ENABLED:
        return {"hits": [], "error": "RAG retrieval is disabled"}
    if not isinstance(query, str) or not query.strip():
        return {"hits": [], "error": "Empty query"}
    try:
        hits = rag.search(query, k=k)
    except Exception as exc:
        logger.exception("rag.search failed: %s", exc)
        return {"hits": [], "error": f"Retrieval failed: {exc}"}
    return {"hits": hits}
