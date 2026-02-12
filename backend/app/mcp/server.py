"""FastMCP server exposing tools for the AI agent (e.g. get_user_email)."""

from uuid import UUID

from fastmcp import FastMCP
from sqlalchemy import select

from app.db.models.user import User
from app.db.session import AsyncSessionLocal

mcp = FastMCP("Relohelp MCP Server")


@mcp.tool
async def get_user_email(user_id: str) -> dict:
    """Returns the authenticated user's email.

    Args:
        user_id: The UUID of the user whose email to retrieve.
    """
    try:
        uid = UUID(user_id)
    except ValueError:
        return {"email": "", "error": "Invalid user_id format"}
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == uid))
        user = result.scalar_one_or_none()
        if not user:
            return {"email": "", "error": "User not found"}
        return {"email": user.email or ""}
