# Relohelp

AI-assisted relocation helper. Combines a FastAPI backend (auth + chat), a React frontend, a Telegram scraper, a RAG pipeline over Telegram threads, and an MCP server that exposes retrieval tools to the agent.

## What we are building

https://www.notion.so/MVP-description-and-App-Architecture-3055ee5a340e80729cacc041f45b513c

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
cp .env.example .env                 # root: INTERNAL_API_TOKEN, RAG/ollama vars
cp backend/.env.example backend/.env # backend runtime config
docker compose up --build
```

Brings up `backend` (8000), `mcp` (8001), `db` (Postgres 18, 5432), `nginx` (80, serving the built frontend). Backend runs migrations on startup.

Ollama is **not** containerized. Install on the host and pull the embedding model:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve
ollama pull mxbai-embed-large
```

The `mcp` service reaches the host via `host.docker.internal` (mapped to `host-gateway`).

### Run locally

**Backend**

```bash
cd backend
uv sync
cp .env.example .env   # set DB_* and any optional API keys
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Requires PostgreSQL 15+ with DB/user matching `backend/.env`.

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
