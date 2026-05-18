"""
Batch-export many Telegram chats from ``chats.json`` into one CSV, with throttling
and JSON bookkeeping (last_parse_date, skip if parsed <10 days ago).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import logging.config
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl import functions, types
from telethon.tl.custom.message import Message
from telethon.tl.types import Channel, Chat

from .export import (
    CSV_FIELDNAMES,
    DEFAULT_SLEEP_BETWEEN_MESSAGES_DURATION_SEC,
    DEFAULT_SLEEP_BETWEEN_MESSAGES_NUMBER,
    _date_created_iso,
    _env_int,
    coerce_chat_entity,
    fetch_linked_channel_posts,
    write_message_row,
    write_messages_from_peer,
)

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CHATS_JSON = _PROJECT_ROOT / "chats.json"
_DEFAULT_MERGED_CSV = _PROJECT_ROOT / "merged_chat_export.csv"

# Skip a chat if it was successfully parsed within this many days.
SKIP_IF_PARSED_WITHIN_DAYS = 10

# Fetch at most this many pinned messages before the main history pass.
MAX_PINNED_TO_FETCH = 10

LOG = logging.getLogger("telegram_scrapper.batch")

# Console (coloredlogs); must match file formatter in logging.ini for parity.
_COLORED_CONSOLE_FMT = (
    "%(asctime)s %(levelname)-8s %(name)-10s %(message)s (%(filename)s %(funcName)s:%(lineno)s)"
)


def to_full_chat_id(raw: str | int | None) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    n = int(s) if s.lstrip("-").isdigit() else None
    if n is None:
        return None
    if s.startswith("-100"):
        return int(s)
    if s.startswith("-"):
        return int(s)
    return -1000000000000 - int(s)


def peer_from_entry(entry: dict[str, Any]) -> int | str:
    link = (entry.get("link") or "").strip()
    if link:
        tail = link.rstrip("/").split("/")[-1]
        if tail.startswith("+") or "joinchat" in link:
            return link
        slug = tail.split("?")[0]
        if slug and not slug.isdigit():
            return slug if slug.startswith("@") else slug
    tid = entry.get("id")
    if tid is None:
        raise ValueError("chat entry needs link or id")
    full = to_full_chat_id(tid)
    if full is None:
        raise ValueError(f"bad id: {tid!r}")
    return coerce_chat_entity(full)


def parse_iso_date(s: str | None) -> datetime | None:
    if not s or not str(s).strip():
        return None
    raw = str(s).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_min_date_utc(since_days: float | None, until_date_str: str | None) -> datetime | None:
    """Lower bound on message time (UTC): messages with date >= this instant are kept."""
    now = datetime.now(timezone.utc)
    bounds: list[datetime] = []
    if since_days is not None:
        bounds.append(now - timedelta(days=float(since_days)))
    if until_date_str and str(until_date_str).strip():
        ud = datetime.strptime(until_date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        bounds.append(ud)
    if not bounds:
        return None
    return max(bounds)


def log_date_floor_settings(
    since_days: float | None,
    until_date_str: str | None,
    effective_min: datetime | None,
) -> None:
    now = datetime.now(timezone.utc)
    has_until = bool(until_date_str and str(until_date_str).strip())
    has_since = since_days is not None
    if has_since:
        d = now - timedelta(days=float(since_days))
        LOG.info(
            "--since-days=%s -> UTC floor %s (same calendar day as --until-date %s)",
            since_days,
            d.isoformat(),
            d.strftime("%Y-%m-%d"),
        )
    if has_until:
        p = datetime.strptime(until_date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        LOG.info(
            "--until-date=%s -> UTC midnight %s",
            until_date_str.strip(),
            p.isoformat(),
        )
    if has_since and has_until and effective_min is not None:
        LOG.info(
            "Both set: using the later (stricter) UTC floor %s (calendar %s)",
            effective_min.isoformat(),
            effective_min.strftime("%Y-%m-%d"),
        )


async def collect_pinned_messages(client: TelegramClient, entity: Any, max_pins: int) -> list[Message]:
    """
    Best-effort pinned messages (up to ``max_pins``).

    Prefer ``iter_messages`` with ``InputMessagesFilterPinned`` when the layer
    supports multiple pins; fall back to ``InputMessagePinned`` / full-chat pin id.
    """
    out: list[Message] = []
    seen: set[int] = set()

    def take(m: Message | None) -> None:
        if m and isinstance(m, Message) and m.id not in seen:
            seen.add(m.id)
            out.append(m)

    try:
        from telethon.tl.types import InputMessagesFilterPinned

        async for m in client.iter_messages(
            entity, filter=InputMessagesFilterPinned(), limit=max_pins
        ):
            take(m)
        if out:
            return out[:max_pins]
    except Exception as e:
        LOG.debug("InputMessagesFilterPinned iter failed: %s", e)

    try:
        res = await client.get_messages(entity, ids=types.InputMessagePinned())
        if isinstance(res, list):
            for x in res:
                take(x if isinstance(x, Message) else None)
        else:
            take(res if isinstance(res, Message) else None)
    except Exception as e:
        LOG.debug("InputMessagePinned failed: %s", e)

    if len(out) >= max_pins:
        return out[:max_pins]

    try:
        if isinstance(entity, Channel):
            full = await client(functions.channels.GetFullChannelRequest(entity))
            pm = getattr(full.full_chat, "pinned_msg_id", None) or None
            if pm:
                m2 = await client.get_messages(entity, ids=pm)
                take(m2 if isinstance(m2, Message) else None)
        elif isinstance(entity, Chat):
            full = await client(functions.messages.GetFullChatRequest(chat_id=entity.id))
            pm = getattr(full.full_chat, "pinned_msg_id", None) or None
            if pm:
                m2 = await client.get_messages(entity, ids=pm)
                take(m2 if isinstance(m2, Message) else None)
    except Exception as e:
        LOG.debug("GetFull* pinned_msg_id failed: %s", e)

    return out[:max_pins]


def load_chats(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_chats(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def has_any_json_limit(chats: list[dict[str, Any]]) -> bool:
    for c in chats:
        v = c.get("number_of_messages")
        if v is not None and int(v) > 0:
            return True
    return False


def validate_constraints(
    cli_limit: int | None,
    since_days: int | None,
    until_date: str | None,
    chats: list[dict[str, Any]],
) -> None:
    if cli_limit is not None or since_days is not None or (until_date and str(until_date).strip()):
        return
    if has_any_json_limit(chats):
        return
    raise SystemExit(
        "Need at least one stopping criterion: --limit, --since-days, --until-date, "
        "or number_of_messages on chat entries in JSON."
    )


def effective_limit(entry: dict[str, Any], cli_limit: int | None) -> int | None:
    chat_lim: int | None = None
    v = entry.get("number_of_messages")
    if v is not None:
        try:
            n = int(v)
            chat_lim = n if n > 0 else None
        except (TypeError, ValueError):
            pass
    if cli_limit is not None and chat_lim is not None:
        return min(cli_limit, chat_lim)
    if cli_limit is not None:
        return cli_limit
    return chat_lim


async def run_batch(args: argparse.Namespace) -> None:
    cfg_path = Path(args.config)
    out_csv = Path(args.output)
    data = load_chats(cfg_path)
    chats: list[dict[str, Any]] = list(data.get("chats") or [])

    validate_constraints(args.limit, args.since_days, args.until_date, chats)

    min_date_utc = compute_min_date_utc(args.since_days, args.until_date)
    log_date_floor_settings(args.since_days, args.until_date, min_date_utc)

    api_id = _env_int("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    session_name = os.getenv("TELEGRAM_SESSION_NAME") or "telegram_scraper"
    if not api_id or not api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")

    session_path = _PROJECT_ROOT / session_name
    client = TelegramClient(str(session_path), api_id, api_hash)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    delimiter = "\t" if args.tsv else ","
    fieldnames = CSV_FIELDNAMES

    await client.start()
    try:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()

            for i, entry in enumerate(chats):
                name = entry.get("name") or entry.get("link") or "?"
                country = entry.get("country") or "?"
                last_raw = entry.get("last_parse_date")
                last_dt = parse_iso_date(str(last_raw) if last_raw is not None else None)
                now = datetime.now(timezone.utc)

                if (
                    not args.force_rerun
                    and last_dt is not None
                    and (now - last_dt) < timedelta(days=SKIP_IF_PARSED_WITHIN_DAYS)
                ):
                    LOG.info(
                        "Skip %s (%s): last_parse_date=%s (< %s days ago)",
                        name,
                        country,
                        last_dt.isoformat(),
                        SKIP_IF_PARSED_WITHIN_DAYS,
                    )
                    continue

                try:
                    peer = peer_from_entry(entry)
                except Exception as e:
                    LOG.exception("Bad config for chat %s (%s): %s", name, country, e)
                    continue

                lim = effective_limit(entry, args.limit)
                if lim is None and min_date_utc is None:
                    LOG.warning(
                        "Skip %s (%s): no per-chat number_of_messages and no date floor "
                        "(--since-days / --until-date); add number_of_messages in JSON or pass --limit / date flags.",
                        name,
                        country,
                    )
                    continue

                LOG.info("Start parse: %s (%s) peer=%r limit=%s min_date_utc=%s", name, country, peer, lim, min_date_utc)

                t0 = datetime.now(timezone.utc)
                seen_ids: set[int] = set()
                rows_pins = 0
                rows_hist = 0
                newest_hist: datetime | None = None
                oldest_hist: datetime | None = None

                try:
                    entity = await client.get_entity(peer)

                    pinned = await collect_pinned_messages(client, entity, MAX_PINNED_TO_FETCH)
                    for pm in pinned:
                        if not write_message_row(writer, pm, seen_ids):
                            continue
                        rows_pins += 1
                        if lim is not None and rows_pins >= lim:
                            break

                    linked_from_pins = await fetch_linked_channel_posts(
                        client, entity, pinned, seen_ids
                    )
                    for lm in linked_from_pins:
                        if not write_message_row(writer, lm, seen_ids):
                            continue
                        rows_pins += 1
                        LOG.info(
                            "Included linked post msg_id=%s (referenced from pinned)",
                            lm.id,
                        )
                        if lim is not None and rows_pins >= lim:
                            break

                    if lim is None or rows_pins < lim:
                        rows_hist, newest_hist, oldest_hist = await write_messages_from_peer(
                            client,
                            peer,
                            writer,
                            seen_ids,
                            limit=lim,
                            min_date_utc=min_date_utc,
                            count_before=rows_pins,
                            sleep_between_messages_number=args.sleep_between_messages_number,
                            sleep_between_messages_duration=args.sleep_between_messages_duration,
                        )

                    rows_total = rows_pins + rows_hist
                    t1 = datetime.now(timezone.utc)

                    parts: list[str] = []
                    if lim is not None and rows_total >= lim:
                        parts.append("limit")
                    if min_date_utc is not None:
                        parts.append("date_floor")
                    reason = "+".join(parts) if parts else "exhausted_or_empty"

                    range_note = ""
                    if oldest_hist is not None and newest_hist is not None:
                        range_note = (
                            f" history_dates=[{oldest_hist.isoformat()} .. {newest_hist.isoformat()}]"
                            " (pinned/linked excluded from oldest)"
                        )

                    LOG.info(
                        "Finished %s (%s): stop=%s rows=%s duration_sec=%.1f%s",
                        name,
                        country,
                        reason,
                        rows_total,
                        (t1 - t0).total_seconds(),
                        range_note,
                    )

                    entry["last_parse_date"] = now.isoformat()
                    entry["oldest_parsed_message_date"] = (
                        oldest_hist.isoformat() if oldest_hist is not None else None
                    )
                    entry["newest_parsed_message_date"] = (
                        newest_hist.isoformat() if newest_hist is not None else None
                    )
                    entry["parsed_messages"] = rows_total
                    save_chats(cfg_path, data)

                except Exception as e:
                    LOG.exception("Parse failed for %s (%s): %s", name, country, e)
                    continue

                if i < len(chats) - 1 and args.sleep_between_chats > 0:
                    LOG.info("Sleep %s s before next chat", args.sleep_between_chats)
                    await asyncio.sleep(args.sleep_between_chats)

    finally:
        await client.disconnect()

    LOG.info("Wrote %s", out_csv)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Export all chats from chats.json into one CSV (Telethon).",
    )
    p.add_argument("--config", type=str, default=str(_DEFAULT_CHATS_JSON), help="Path to chats.json")
    p.add_argument("-o", "--output", type=str, default=str(_DEFAULT_MERGED_CSV), help="Merged CSV path")
    p.add_argument(
        "--force-rerun",
        action="store_true",
        help="Re-parse every chat even if last_parse_date is within the skip window (default: skip if <10 days).",
    )
    p.add_argument(
        "--sleep-between-chats",
        type=float,
        default=60.0,
        help="Seconds to sleep between chats (default: 60).",
    )
    p.add_argument(
        "--sleep-between-messages-number",
        type=int,
        default=DEFAULT_SLEEP_BETWEEN_MESSAGES_NUMBER,
        help="Pause after every N messages within one chat (default: 500). Set 0 to disable.",
    )
    p.add_argument(
        "--sleep-between-messages-duration",
        type=float,
        default=DEFAULT_SLEEP_BETWEEN_MESSAGES_DURATION_SEC,
        help="Seconds to sleep after each in-chat batch (default: 10). Ignored if --sleep-between-messages-number is 0.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap per chat: effective = min(this, number_of_messages in JSON). If JSON has no limit, uses this value alone.",
    )
    p.add_argument(
        "--since-days",
        type=float,
        default=None,
        help="Only messages with date >= now (UTC) minus this many days. Logged as equivalent --until-date (UTC).",
    )
    p.add_argument(
        "--until-date",
        type=str,
        default=None,
        help="Only messages on/after this calendar date (UTC midnight), YYYY-MM-DD. "
        "If both --since-days and --until-date are set, the stricter (later) floor is used. "
        "Combine with --limit: stop when either hits first.",
    )
    p.add_argument(
        "--logging-config",
        type=str,
        default=str(_PROJECT_ROOT / "logging.ini"),
        help="logging.config fileConfig path (default: telegram_scrapper/logging.ini).",
    )
    p.add_argument("--tsv", action="store_true", help="Tab-separated output.")
    p.add_argument("-v", "--verbose", action="store_true", help="Set root logger to DEBUG after loading config.")
    return p


def _configure_logging(args: argparse.Namespace) -> None:
    import coloredlogs

    log_dir = _PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ini_path = Path(args.logging_config)
    level = logging.DEBUG if args.verbose else logging.INFO

    if ini_path.is_file():
        logging.config.fileConfig(
            ini_path,
            defaults={"logfile": str(log_dir / "log.log")},
            disable_existing_loggers=False,
        )
    else:
        logging.root.handlers.clear()

    coloredlogs.install(
        level=level,
        fmt=_COLORED_CONSOLE_FMT,
        stream=sys.stdout,
        isatty=sys.stdout.isatty(),
    )

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        LOG.setLevel(logging.DEBUG)


def main() -> None:
    args = build_arg_parser().parse_args()
    _configure_logging(args)
    LOG.info(
        "Throttling: every %s messages pause %s s; between chats %s s; force_rerun=%s",
        args.sleep_between_messages_number,
        args.sleep_between_messages_duration,
        args.sleep_between_chats,
        args.force_rerun,
    )
    asyncio.run(run_batch(args))


if __name__ == "__main__":
    main()
