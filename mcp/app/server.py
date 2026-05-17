"""FastMCP server exposing tools for the AI agent.

Tools do NOT touch the database directly. They talk to the backend over HTTP
using a shared INTERNAL_API_TOKEN.
"""

from uuid import UUID

import httpx
from fastmcp import FastMCP

from app.config import settings

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
