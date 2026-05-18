# research

Telegram → RAG pipeline experiments. Single [uv](https://docs.astral.sh/uv/) project with optional dependency groups.

## Layout

```
research/
├── pyproject.toml              # uv project + dependency groups (rag, telegram, translate)
├── uv.lock
├── rag_pipeline.py             # marimo: CSV → threads → ollama → ChromaDB
├── translate_csv.py            # CLI: merged.csv → merged.en.csv
├── chroma_db/                  # persistent ChromaDB (created on first RAG run)
└── telegram_scrapper/
    ├── telegram_scrapper/      # Python package (export, batch_export)
    ├── chats.json
    ├── merged.csv              # batch export output (LFS)
    ├── notebooks/csv_readability.py
    └── docs.md
```

## Dependency groups

| Group | Packages | Use |
| --- | --- | --- |
| *(default)* | `marimo`, `pandas` | notebooks / CSV tooling |
| `telegram` | `telethon`, `python-dotenv`, `coloredlogs` | scraper CLI |
| `rag` | `chromadb`, `ollama`, `tqdm` | RAG pipeline notebook |
| `translate` | `deep-translator`, `langdetect` | `translate_csv.py` |

```bash
cd research
uv sync --all-groups          # everything
uv sync --group telegram      # scraper only
uv sync --group rag           # RAG only
```

## Telegram scraper

See `telegram_scrapper/docs.md`.

```bash
uv sync --group telegram
cp telegram_scrapper/.env.example telegram_scrapper/.env
uv run python -m telegram_scrapper.batch_export --help
```

## RAG pipeline

```bash
uv sync --group rag
uv run marimo edit rag_pipeline.py
```

Requires host [ollama](https://ollama.com/) with `mxbai-embed-large` (`ollama pull mxbai-embed-large`).

## CSV translation

```bash
uv sync --group translate
uv run python translate_csv.py --in telegram_scrapper/merged.csv --out telegram_scrapper/merged.en.csv
```

## CSV schema (`merged.csv`)

| column | description |
| --- | --- |
| `text_or_caption` | message body or media caption |
| `msg_id` | Telegram message id (stable per chat) |
| `reply_to` | parent `msg_id` if reply, else null |
| `chat_id` | source chat id |
| `date_created` | ISO 8601, UTC |

## Requirements

- Python ≥ 3.13, `uv`
- Git LFS (for `telegram_scrapper/merged.csv`)
- ollama on host for RAG
