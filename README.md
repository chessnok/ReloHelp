# Relohelp

AI-assisted relocation helper. Combines a FastAPI backend (auth + chat), a React frontend, a Telegram scraper, a RAG pipeline over Telegram threads, and an MCP server that exposes retrieval tools to the agent.

## What we are building

https://hazel-watcher-e79.notion.site/App-Architecture-3055ee5a340e80729cacc041f45b513c?source=copy_link

## Stack

- **Frontend**: React 19, TypeScript, Vite, React Router, shadcn/ui, Tailwind. Cookie-based auth (access + refresh).
- **Backend**: FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL. Users/sessions, email verification + password reset, chat endpoints, OpenAI integration.
- **MCP server**: FastMCP. Exposes agent-callable tools (Telegram RAG retrieval, Firecrawl lookup). Talks to backend over HTTP, never to the DB.
- **RAG pipeline**: ollama (`mxbai-embed-large`) + ChromaDB. Embeds Telegram threads into a local vector store.
- **Telegram scraper**: Telethon-based exporter, single-chat + batch modes, merged CSV output.
- **Infrastructure**: PostgreSQL, Docker Compose for the full stack. Ollama runs on the host (not in compose). Optional: Resend (email), OpenAI, Langfuse, Firecrawl.

## Repository layout

| Path                          | Purpose                                                        |
| ----------------------------- | -------------------------------------------------------------- |
| `backend/`                    | FastAPI app — auth, chat, MCP client                           |
| `frontend/`                   | React 19 + Vite SPA, served by Nginx in compose                |
| `mcp/`                        | Standalone FastMCP server (agent tools)                        |
| `research/`                   | RAG pipeline (marimo notebook) + Telegram scraper              |
| `research/telegram_scrapper/` | Telethon export scripts (`export.py`, `batch_export.py`)       |
| `research/rag_pipeline.py`    | marimo notebook: CSV → threads → ollama embeddings → ChromaDB  |
| `docker-compose.yml`          | Orchestrates backend, mcp, db, nginx                           |
| `.env.example`                | Root env (compose interpolation: shared token, RAG vars)       |
| `backend/.env.example`        | Backend runtime config (DB, Resend, OpenAI, Langfuse, MCP URL) |

## Setup

### Run with Docker Compose

Prerequisites: Docker (24+) and Compose Plugin v2.

```bash
cd research/telegram_scrapper
uv sync
cp .env.example .env   # TELEGRAM_API_ID, TELEGRAM_API_HASH
```
#### Run single chat
```bash
cd research/telegram_scrapper
uv run python -m telegram_scrapper.export -1001350470024 --limit 1500 -o ./my_export.csv
```
#### Run multiple chats
```bash
cd research/telegram_scrapper
uv run python -m telegram_scrapper.batch_export \
  --force-rerun \
  --since-days 360 \
  --sleep-between-chats 15 \
  --sleep-between-messages-number 500 \
  --sleep-between-messages-duration 10 \
  -o merged.csv
```

Requires PostgreSQL 15+ with DB/user matching `backend/.env`.

#### Check CSV (marimo)
```bash
cd research/telegram_scrapper
uv run marimo edit notebooks/csv_readability.py
```

See `research/telegram_scrapper/docs.md` for CLI flags and export behavior.
**Frontend**

```bash
cd frontend
npm install
npm run dev
```

**MCP server**

```bash
cd mcp
uv sync
uv run python -m app.run_server
```

See `mcp/README.md` for env vars (`MCP_PORT`, `BACKEND_URL`, `INTERNAL_API_TOKEN`, `REQUEST_TIMEOUT_SECONDS`).

## Research workflows

### Telegram scraper (`research/telegram_scrapper/`)

Standalone Python module with its own `requirements.txt`.

```bash
cd research/telegram_scrapper
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
source .venv/bin/activate
```

Single chat:

```bash
python export.py -1001350470024 --limit 1500 -o ./my_export.csv
```

Batch (from repo root):

```bash
python -m research.telegram_scrapper.batch_export \
  --force-rerun \
  --since-days 360 \
  --sleep-between-chats 15 \
  --sleep-between-messages-number 500 \
  --sleep-between-messages-duration 10 \
  -o merged.csv
```

Per chat the effective row cap is `min(--limit, number_of_messages in chats.json)` when both are set. Full flag reference: `research/telegram_scrapper/docs.md`. Logging config: `research/telegram_scrapper/logging.ini` (console + `research/telegram_scrapper/logs/log.log`).

Validate the merged CSV:

```bash
python3 research/telegram_scrapper/check_scv_readability.py
```

`merged.csv` is tracked via Git LFS.

### RAG pipeline (`research/rag_pipeline.py`)

marimo notebook. CSV → thread reconstruction → ollama `mxbai-embed-large` → ChromaDB collection `tg_threads`.

```bash
cd research
uv sync
uv run marimo edit rag_pipeline.py
```

Needs the host ollama running (`ollama serve`) with `mxbai-embed-large` pulled. Output: `research/chroma_db/` (used by the `mcp` retrieval tool when `RAG_ENABLED=true`).

## Requirements

- **Backend / MCP / research**: Python 3.13, `uv`, PostgreSQL 15+.
- **Frontend**: Node.js 20+, npm.
- **RAG**: ollama on the host with `mxbai-embed-large`.
- **Optional**: Resend (email), OpenAI key (chat), Langfuse (observability), Firecrawl (MCP web tool).

## Features

- Registration + login (cookie-based access + refresh tokens).
- Email verification + password reset (require Resend).
- Protected routes, dashboard scaffold.
- Chat endpoints backed by OpenAI; agent calls MCP tools (Telegram RAG, Firecrawl).
- Health check: `GET /ping`.

## Git

Short-lived feature branches off `master`; open PRs for changes.
