"""Run the MCP server (HTTP transport). Use: uv run python -m app.run_server"""

from app.config import settings
from app.server import mcp

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=settings.MCP_PORT)
