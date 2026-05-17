# research

Telegram → RAG pipeline experiments.

Two parts:

1. **`telegram_scrapper/`** — exports messages from Telegram chats into `merged.csv`.
2. **`rag_pipeline.py`** — marimo notebook that turns `merged.csv` into embeddings stored in a local ChromaDB collection and runs sample RAG queries.

## Layout

```
research/
├── pyproject.toml          # uv-managed deps (marimo, chromadb, ollama, pandas, tqdm)
├── rag_pipeline.py         # marimo notebook: CSV → threads → embeddings → ChromaDB → query
├── merged.csv              # exported chat messages (LFS, produced by telegram_scrapper)
├── chroma_db/              # persistent ChromaDB store (created on first run)
└── telegram_scrapper/      # Telegram exporter (see its own docs.md)
    ├── export.py
    ├── batch_export.py
    ├── chats.json
    └── requirements.txt
```

## Requirements

- Python ≥ 3.13
- [uv](https://docs.astral.sh/uv/) for dependency management
- [ollama](https://ollama.com/) running locally with the `mxbai-embed-large` model pulled:
  ```bash
  ollama pull mxbai-embed-large
  ```
- Git LFS (for `merged.csv`)

## Setup

```bash
cd research
uv sync
```

## Running the pipeline

```bash
uv run marimo edit rag_pipeline.py
```

The notebook executes top-to-bottom:

1. Load `telegram_scrapper/merged.csv`, drop empty `text_or_caption`, parse `date_created` as UTC, sort by `(chat_id, date_created)`.
2. **Thread reconstruction.** Messages sharing `(chat_id, reply_to)` are merged into one document (`kind=thread`, id = `thread:{chat_id}:{reply_to}`). Standalone messages become their own document (`kind=single`, id = `single:{chat_id}:{msg_id}`).
3. **Embed.** `ollama.embed` with `mxbai-embed-large`. Texts trimmed to 600 chars (300-char fallback on error). Dim 1024.
4. **Store.** Persistent ChromaDB at `chroma_db/`, cosine space, collection `tg_threads`. Idempotent: existing `doc_id`s are skipped.
5. **Query.** `rag_query("...", k=5)` returns `id`, `distance`, `metadata`, and snippet.

By default the notebook ingests only **50** docs as a smoke test. For a full ingest set `n_test_sample = None` in the ingest cell.

## CSV schema

`merged.csv` columns:

| column | description |
| --- | --- |
| `text_or_caption` | message body or media caption |
| `msg_id` | Telegram message id (stable per chat) |
| `reply_to` | parent `msg_id` if reply, else null |
| `chat_id` | source chat id |
| `date_created` | ISO 8601, UTC |

`doc_id`s are derived from `chat_id` + `msg_id` / `reply_to`, so they survive CSV re-sorts and re-runs.

## Re-scraping

See `telegram_scrapper/docs.md`. After producing a new `merged.csv`, re-run the notebook — already-ingested `doc_id`s are skipped, new docs are added.
