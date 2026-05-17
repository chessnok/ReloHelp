"""Translate the `text_or_caption` column of merged.csv to English via Google Translate.

Usage:
    uv run python translate_csv.py --in merged.csv --out merged.en.csv

Strategy
--------
- Read input CSV.
- For each non-empty row: skip if text already detected English (langdetect),
  else translate via deep_translator.GoogleTranslator.
- Parallelize with ThreadPoolExecutor(WORKERS).
- Resume: writes a sidecar `<out>.tmp` row-by-row; on restart, skips already-done
  (chat_id, msg_id). Final atomic rename when complete.

Rate limits
-----------
The unofficial Google Translate endpoint behind deep_translator is rate-limited.
Expect ~5 req/s sustained, retries on 429/503.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from deep_translator import GoogleTranslator
from langdetect import DetectorFactory, detect_langs
from tqdm import tqdm

DetectorFactory.seed = 0  # deterministic langdetect

GT_MAX_CHARS = 4500  # Google free endpoint hard limit ~5000
MIN_TRANSLATE_LEN = 4  # skip emoji / one-word rows


def _is_english(text: str) -> bool:
    try:
        langs = detect_langs(text)
    except Exception:
        return False
    return any(lp.lang == "en" and lp.prob >= 0.85 for lp in langs)


def _split_long(text: str, limit: int) -> list[str]:
    """Greedy split on sentence punctuation, then newline, then hard cut."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf = text
    while len(buf) > limit:
        cut = max(
            buf.rfind(". ", 0, limit),
            buf.rfind("! ", 0, limit),
            buf.rfind("? ", 0, limit),
            buf.rfind("\n", 0, limit),
        )
        if cut == -1:
            cut = limit
        parts.append(buf[:cut])
        buf = buf[cut:]
    if buf:
        parts.append(buf)
    return parts


def _translate_one(translator: GoogleTranslator, text: str, retries: int = 4) -> str:
    """Translate one string, splitting on length and retrying on transient errors."""
    chunks = _split_long(text, GT_MAX_CHARS)
    out: list[str] = []
    for chunk in chunks:
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                translated = translator.translate(chunk) or ""
                out.append(translated)
                break
            except Exception as exc:
                last_err = exc
                time.sleep(0.5 * (2**attempt))
        else:
            raise RuntimeError(f"translate failed after {retries} retries: {last_err}")
    return "".join(out)


def _load_done(tmp_path: Path) -> set[tuple[int, int]]:
    if not tmp_path.exists():
        return set()
    try:
        df = pd.read_csv(
            tmp_path,
            usecols=["msg_id", "chat_id"],
        )
    except Exception:
        return set()
    return set(
        zip(
            pd.to_numeric(df["chat_id"], errors="coerce").astype("Int64").tolist(),
            pd.to_numeric(df["msg_id"], errors="coerce").astype("Int64").tolist(),
        )
    )


def _row_key(row: dict) -> tuple[int, int]:
    return (int(row["chat_id"]), int(row["msg_id"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--out", dest="out_path", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--src", default="auto")
    parser.add_argument("--dst", default="en")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s | %(message)s",
    )
    log = logging.getLogger("translate")

    df = pd.read_csv(args.in_path)
    log.info("Loaded %d rows from %s", len(df), args.in_path)

    if args.limit is not None:
        df = df.head(args.limit)
        log.info("Limited to %d rows", len(df))

    tmp_path = args.out_path.with_suffix(args.out_path.suffix + ".tmp")
    done = _load_done(tmp_path)
    if done:
        log.info("Resuming: %d rows already translated in %s", len(done), tmp_path)

    cols = list(df.columns)
    write_header = not tmp_path.exists()
    f = tmp_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=cols)
    if write_header:
        writer.writeheader()

    pending: list[dict] = []
    for r in df.to_dict(orient="records"):
        if pd.isna(r.get("msg_id")) or pd.isna(r.get("chat_id")):
            continue
        if _row_key(r) in done:
            continue
        pending.append(r)

    log.info("Translating %d rows with %d workers", len(pending), args.workers)

    def _process(row: dict) -> dict:
        translator = GoogleTranslator(source=args.src, target=args.dst)
        text = row.get("text_or_caption")
        if not isinstance(text, str) or len(text.strip()) < MIN_TRANSLATE_LEN:
            return row
        if _is_english(text):
            return row
        try:
            row["text_or_caption"] = _translate_one(translator, text)
        except Exception as exc:
            log.warning(
                "row chat=%s msg=%s failed: %s",
                row.get("chat_id"),
                row.get("msg_id"),
                exc,
            )
        return row

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(_process, r) for r in pending]
            for fut in tqdm(
                as_completed(futures), total=len(futures), desc="translate"
            ):
                out_row = fut.result()
                writer.writerow(out_row)
                f.flush()
    finally:
        f.close()

    tmp_path.replace(args.out_path)
    log.info("Done. Wrote %s", args.out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
