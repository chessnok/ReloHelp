# Relohelp MCP Server

Standalone FastMCP service. Exposes tools for the AI agent. Talks to the backend
over HTTP — does **not** access the database directly.

## Tools

| Tool | Purpose |
|---|---|
| `get_user_email` | Returns the authenticated user's email (backend-injected `user_id`). |
| `search_telegram_chats` | Top-k semantic search over indexed Telegram relocation/visa chats. Hits include `chat_id`, `date_min`, `date_max` for source attribution. |
| `find_official_info` | Firecrawl-backed web search for fresh, official sources (visas, taxes, regulations). |

## Environment

| Var | Default | Purpose |
|---|---|---|
| `MCP_PORT` | `8001` | Port the HTTP transport binds to |
| `BACKEND_URL` | `http://backend:8000` | Base URL of the backend service |
| `INTERNAL_API_TOKEN` | _(unset)_ | Shared secret sent as `X-Internal-Token` header |
| `REQUEST_TIMEOUT_SECONDS` | `5.0` | Per-request timeout |
| `RAG_ENABLED` | `true` | Disable to make `search_telegram_chats` return an error stub |
| `CHROMA_DIR` | `/data/chroma` | Persistent ChromaDB directory |
| `CHROMA_COLLECTION` | `tg_threads` | Collection name |
| `OLLAMA_HOST` | `http://ollama:11434` | Ollama base URL (must be reachable from the container) |
| `OLLAMA_EMBED_MODEL` | `mxbai-embed-large` | Embedding model name |
| `RAG_DEFAULT_K` | `5` | Default top-k |
| `RAG_MAX_K` | `20` | Hard ceiling on `k` |
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

Built and orchestrated via the root `docker-compose.yml` `mcp` service. The
`chroma_data` named volume holds the persistent vector store.

## RAG: ingesting Telegram chats

The retrieval index is built offline from the scraper's `merged.csv`. Schema (per
the scraper update from Valik on PR #22):

```
text_or_caption, msg_id, reply_to, chat_id, date_created
```

`date_created` is ISO 8601 UTC. Threads are reconstructed by walking the
`msg_id` <-> `reply_to` chain inside each chat: roots become "thread" docs
(root + descendants joined chronologically), childless roots become "single"
docs.

### Prerequisites

1. Run `ollama serve` somewhere reachable from the MCP container and pull the
   model: `ollama pull mxbai-embed-large`.
2. Make `merged.csv` available to the container (mount the scraper output dir,
   or copy it in).

### Ingest

```bash
# In the running container (or local venv):
uv run python -m app.rag_ingest --csv /data/merged.csv

# Sample run first:
uv run python -m app.rag_ingest --csv /data/merged.csv --limit 100
```

Re-running is safe: doc_ids already in the collection are skipped, so the CLI
acts as an incremental upsert.

### Notes

- The image grows ~1 GB because of `chromadb` + `onnxruntime`. Acceptable for
  MVP; revisit if it becomes painful.
- `ollama` is intentionally **not** in `docker-compose.yml`; run it on the host
  (compose maps `host.docker.internal` automatically) or point `OLLAMA_HOST` at
  a hosted instance.
