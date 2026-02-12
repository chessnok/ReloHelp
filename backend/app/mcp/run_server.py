"""Run the MCP server (HTTP transport). Use: uv run python -m app.mcp.run_server"""

from app.core.config import settings
from app.mcp.server import mcp

if __name__ == "__main__":
    import urllib.parse

    url = settings.MCP_SERVER_URL
    parsed = urllib.parse.urlsplit(url)
    port = parsed.port or 8001
    mcp.run(transport="http", host="0.0.0.0", port=port)
