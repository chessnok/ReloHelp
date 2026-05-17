"""
Export one Telegram chat into a single UTF-8 CSV.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import re
import sys
from datetime import timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.custom.message import Message
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
from telethon.utils import get_peer_id

if TYPE_CHECKING:
    from datetime import datetime

load_dotenv()

_DEFAULT_CSV = Path(__file__).resolve().parent / "chat_export.csv"

# Defaults for throttling inside one chat (batch export); override via CLI.
DEFAULT_SLEEP_BETWEEN_MESSAGES_NUMBER = 500
DEFAULT_SLEEP_BETWEEN_MESSAGES_DURATION_SEC = 10.0

CSV_FIELDNAMES = ("text_or_caption", "msg_id", "reply_to", "chat_id", "date_created")

# t.me/channel/123 or t.me/c/1136040934/123
_TME_POST_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/(?:(c)/)?([A-Za-z0-9_]+)/(\d+)",
    re.IGNORECASE,
)


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


def message_to_csv_row(message: Message) -> dict[str, str | int]:
    return {
        "text_or_caption": _message_text_or_caption(message),
        "msg_id": message.id,
        "reply_to": _reply_to_id(message),
        "chat_id": _chat_id(message),
        "date_created": _date_created_iso(message),
    }


def _link_matches_entity(slug: str, is_c_format: bool, entity: Any) -> bool:
    peer_id = get_peer_id(entity)
    if is_c_format:
        try:
            internal = int(slug)
        except ValueError:
            return False
        linked_peer = int(f"-100{internal}") if internal > 0 else internal
        return peer_id == linked_peer
    username = getattr(entity, "username", None)
    if not username:
        return False
    return slug.lower() == username.lower().lstrip("@")


def post_ids_from_channel_links(message: Message, entity: Any) -> list[int]:
    """Message ids for t.me post URLs that point at the same channel as ``entity``."""
    text = message.text or message.message or ""
    blobs: list[str] = [text] if text else []
    for ent in message.entities or []:
        if isinstance(ent, MessageEntityTextUrl):
            blobs.append(ent.url)
        elif isinstance(ent, MessageEntityUrl) and text:
            blobs.append(text[ent.offset : ent.offset + ent.length])

    ids: list[int] = []
    seen: set[int] = set()
    for blob in blobs:
        for match in _TME_POST_LINK_RE.finditer(blob):
            is_c, slug, msg_id = match.group(1), match.group(2), int(match.group(3))
            if _link_matches_entity(slug, bool(is_c), entity) and msg_id not in seen:
                seen.add(msg_id)
                ids.append(msg_id)
    return ids


async def fetch_channel_posts_by_ids(
    client: TelegramClient,
    entity: Any,
    message_ids: list[int],
) -> list[Message]:
    if not message_ids:
        return []
    out: list[Message] = []
    for i in range(0, len(message_ids), 100):
        batch = message_ids[i : i + 100]
        res = await client.get_messages(entity, ids=batch)
        items = res if isinstance(res, list) else [res]
        for m in items:
            if isinstance(m, Message):
                out.append(m)
    return out


async def fetch_linked_channel_posts(
    client: TelegramClient,
    entity: Any,
    source_messages: list[Message],
    seen_message_ids: set[int],
) -> list[Message]:
    """Fetch posts linked from pinned/hub messages (same-channel t.me post URLs)."""
    wanted: list[int] = []
    local_seen: set[int] = set()
    for msg in source_messages:
        for mid in post_ids_from_channel_links(msg, entity):
            if mid in seen_message_ids or mid in local_seen:
                continue
            local_seen.add(mid)
            wanted.append(mid)
    return await fetch_channel_posts_by_ids(client, entity, wanted)


def write_message_row(
    writer: csv.DictWriter,
    message: Message,
    seen_message_ids: set[int],
) -> bool:
    if message.id in seen_message_ids:
        return False
    body = _message_text_or_caption(message)
    if not body:
        return False
    writer.writerow(message_to_csv_row(message))
    seen_message_ids.add(message.id)
    return True


def _message_dt_utc(message: Message) -> "datetime":
    from datetime import datetime as dtmod

    d: dtmod = message.date
    if d.tzinfo is None:
        return d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


async def write_messages_from_peer(
    client: TelegramClient,
    peer: Any,
    writer: csv.DictWriter,
    seen_message_ids: set[int],
    *,
    limit: int | None,
    min_date_utc: "datetime | None",
    count_before: int = 0,
    sleep_between_messages_number: int = DEFAULT_SLEEP_BETWEEN_MESSAGES_NUMBER,
    sleep_between_messages_duration: float = DEFAULT_SLEEP_BETWEEN_MESSAGES_DURATION_SEC,
) -> tuple[int, "datetime | None", "datetime | None"]:
    """
    Stream messages newest-first. Writes rows with non-empty text/caption.

    Stops when a message is strictly older than ``min_date_utc`` (if set), or when
    total written (including ``count_before``) reaches ``limit`` (if set).

    Returns ``(rows_written_this_call, newest_written_utc, oldest_written_utc)``.
    """
    from datetime import datetime as dtmod

    written = 0
    newest: dtmod | None = None
    oldest: dtmod | None = None
    since_last_pause = 0
    total = count_before

    async for message in client.iter_messages(peer, reverse=False):
        if not isinstance(message, Message):
            continue
        if message.id in seen_message_ids:
            continue

        md = _message_dt_utc(message)
        if min_date_utc is not None and md < min_date_utc:
            break

        if not write_message_row(writer, message, seen_message_ids):
            continue
        written += 1
        total += 1
        since_last_pause += 1

        if newest is None or md > newest:
            newest = md
        if oldest is None or md < oldest:
            oldest = md

        if limit is not None and total >= limit:
            break

        if (
            sleep_between_messages_duration > 0
            and sleep_between_messages_number > 0
            and since_last_pause >= sleep_between_messages_number
        ):
            since_last_pause = 0
            await asyncio.sleep(sleep_between_messages_duration)

    return written, newest, oldest


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

    CSV columns: text_or_caption, msg_id, reply_to, chat_id, date_created
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

    fieldnames = CSV_FIELDNAMES
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

            seen: set[int] = set()
            async for message in client.iter_messages(peer, **kwargs):
                if not isinstance(message, Message):
                    continue
                write_message_row(writer, message, seen)
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
    import coloredlogs

    coloredlogs.install(
        level=logging.INFO,
        stream=sys.stdout,
        isatty=sys.stdout.isatty(),
    )
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
