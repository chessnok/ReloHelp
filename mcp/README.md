# Relohelp MCP Server

Standalone FastMCP service. Exposes tools for the AI agent. Talks to the backend over HTTP — does **not** access the database directly.

## Environment

| Var | Default | Purpose |
|---|---|---|
| `MCP_PORT` | `8001` | Port the HTTP transport binds to |
| `BACKEND_URL` | `http://backend:8000` | Base URL of the backend service |
| `INTERNAL_API_TOKEN` | _(unset)_ | Shared secret sent as `X-Internal-Token` header |
| `REQUEST_TIMEOUT_SECONDS` | `5.0` | Per-request timeout |

## Run locally

```bash
uv sync
uv run python -m app.run_server
```

## Docker

Built and orchestrated via the root `docker-compose.yml` `mcp` service.
