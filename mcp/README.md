# Relohelp MCP Server

Standalone FastMCP service. Exposes tools for the AI agent. Talks to the backend over HTTP — does **not** access the database directly.

## Environment

| Var | Default | Purpose |
|---|---|---|
| `MCP_PORT` | `8001` | Port the HTTP transport binds to |
| `BACKEND_URL` | `http://backend:8000` | Base URL of the backend service |
| `INTERNAL_API_TOKEN` | _(unset)_ | Shared secret sent as `X-Internal-Token` header |
| `REQUEST_TIMEOUT_SECONDS` | `5.0` | Per-request timeout |
| `FIRECRAWL_API_KEY` | _(unset)_ | API key for Firecrawl (`find_official_info` tool is disabled until set) |
| `FIRECRAWL_API_URL` | `https://api.firecrawl.dev` | Firecrawl base URL. Override for self-hosted |
| `FIRECRAWL_TIMEOUT_SECONDS` | `30.0` | Firecrawl request timeout |
| `FIRECRAWL_SEARCH_LIMIT` | `5` | Default max results per `find_official_info` call |

## Firecrawl setup

`find_official_info` powers fresh, official web lookups (visas, taxes, regulations). Two options:

- **Cloud** — sign up at [firecrawl.dev](https://firecrawl.dev), grab an API key, set `FIRECRAWL_API_KEY`.
- **Self-hosted** — follow the official guide: <https://github.com/firecrawl/firecrawl/blob/main/SELF_HOST.md>. Point `FIRECRAWL_API_URL` at your instance and set `FIRECRAWL_API_KEY` to its configured token.

The MCP server enforces (via `instructions`) that the agent rely **only on new and official sources**.

## Run locally

```bash
uv sync
uv run python -m app.run_server
```

## Docker

Built and orchestrated via the root `docker-compose.yml` `mcp` service.
