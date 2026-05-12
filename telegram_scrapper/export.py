"""
Export one Telegram chat into a single UTF-8 CSV.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
from datetime import timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.custom.message import Message

load_dotenv()

_DEFAULT_CSV = Path(__file__).resolve().parent / "chat_export.csv"


def coerce_chat_entity(chat_id: int | str) -> int | str:
    """
    Telethon resolves plain digit strings via _get_entity_from_string, which often
    fails for numeric peer ids. Passing int uses the correct MTProto peer path.
    """
    if isinstance(chat_id, int):
        return chat_id
    s = str(chat_id).strip()
    if s.startswith("@"):
        return s
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        return int(s)
    return s


def _env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _message_text_or_caption(message: Message) -> str:
    if getattr(message, "action", None):
        return ""
    text = message.text or message.message or ""
    return (text or "").strip()


def _reply_to_id(message: Message) -> str:
    rid = getattr(message, "reply_to_msg_id", None)
    return "" if rid is None else str(rid)


def _chat_id(message: Message) -> str:
    cid = getattr(message, "chat_id", None)
    if cid is None and message.peer_id is not None:
        # Telethon may expose peer; fall back to string of peer
        return str(message.peer_id)
    return str(cid) if cid is not None else ""


def _date_created_iso(message: Message) -> str:
    dt = message.date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


async def export_chat_to_csv(
    chat_id: int | str,
    *,
    csv_path: Path | str = _DEFAULT_CSV,
    api_id: int | None = None,
    api_hash: str | None = None,
    session_name: str | None = None,
    limit: int | None = None,
    append: bool = False,
    delimiter: str = ",",
) -> Path:
    """
    Pull accessible messages from ``chat_id`` and write one CSV table.

    ``chat_id`` can be username (@channel), full supergroup id as int (e.g.
    ``-1001234567890``), or other strings Telethon can resolve. Prefer int or
    ``-100…`` form for groups; bare positive ids may be ambiguous (user vs channel).

    CSV columns: text_or_caption, reply_to, chat_id, date_created
    """
    resolved_api_id = api_id or _env_int("TELEGRAM_API_ID")
    resolved_api_hash = api_hash or os.getenv("TELEGRAM_API_HASH")
    resolved_session = session_name or os.getenv("TELEGRAM_SESSION_NAME") or "telegram_scraper"

    if not resolved_api_id or not resolved_api_hash:
        raise ValueError(
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH (see .env.example) or pass api_id/api_hash."
        )

    out = Path(csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    session_path = Path(__file__).resolve().parent / resolved_session
    client = TelegramClient(str(session_path), resolved_api_id, resolved_api_hash)

    fieldnames = ("text_or_caption", "reply_to", "chat_id", "date_created")
    file_exists = out.exists() and out.stat().st_size > 0

    await client.start()

    peer = coerce_chat_entity(chat_id)

    try:
        mode = "a" if append else "w"
        with out.open(mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            if not append or not file_exists:
                writer.writeheader()

            kwargs: dict[str, Any] = {"reverse": True}
            if limit is not None:
                kwargs["limit"] = limit

            async for message in client.iter_messages(peer, **kwargs):
                if not isinstance(message, Message):
                    continue
                body = _message_text_or_caption(message)
                if not body:
                    continue
                writer.writerow(
                    {
                        "text_or_caption": body,
                        "reply_to": _reply_to_id(message),
                        "chat_id": _chat_id(message),
                        "date_created": _date_created_iso(message),
                    }
                )
    finally:
        await client.disconnect()

    return out


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export Telegram chat messages to CSV (Telethon).")
    p.add_argument(
        "chat_id",
        help="Username (@ch), full group id (-100…), or link; digit strings are parsed as int.",
    )
    p.add_argument(
        "-o",
        "--output",
        default=str(_DEFAULT_CSV),
        help=f"CSV path (default: {_DEFAULT_CSV})",
    )
    p.add_argument("--limit", type=int, default=None, help="Max messages to export (newest first).")
    p.add_argument("--append", action="store_true", help="Append rows instead of overwriting.")
    p.add_argument(
        "--tsv",
        action="store_true",
        help="Tab-separated values (often easier to eyeball when posts contain many commas).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    delim = "\t" if args.tsv else ","
    path = asyncio.run(
        export_chat_to_csv(
            args.chat_id,
            csv_path=args.output,
            limit=args.limit,
            append=args.append,
            delimiter=delim,
        )
    )
    print(path)


if __name__ == "__main__":
    main()
