"""CLI: ingest a Telegram CSV export into the pgvector RAG table.

Usage:
    uv run python -m app.rag_ingest --csv path/to/merged.csv [--limit N] [--batch 32]

The CSV must follow the new scraper schema (per Valik on PR #22):
    text_or_caption, msg_id, reply_to, chat_id, date_created

Already-ingested doc_ids are skipped, so re-running on a larger CSV only embeds
new threads. Safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app import rag


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest Telegram CSV into pgvector RAG table."
    )
    parser.add_argument("--csv", required=True, type=Path, help="Path to merged.csv")
    parser.add_argument("--limit", type=int, default=None, help="Max docs to ingest")
    parser.add_argument("--batch", type=int, default=32, help="Embed batch size")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    log = logging.getLogger("app.rag_ingest")

    if not args.csv.exists():
        log.error("CSV not found: %s", args.csv)
        return 2

    import pandas as pd

    df = pd.read_csv(args.csv)
    log.info("Loaded %d rows from %s", len(df), args.csv)

    docs = rag.build_threads(df)
    log.info(
        "Built %d docs (threads=%d singles=%d)",
        len(docs),
        sum(1 for d in docs if d["kind"] == "thread"),
        sum(1 for d in docs if d["kind"] == "single"),
    )

    if args.limit is not None:
        docs = docs[: args.limit]
        log.info("Limited to %d docs", len(docs))

    written = rag.ingest(docs, batch_size=args.batch)
    log.info("Ingest complete: %d new docs written", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
