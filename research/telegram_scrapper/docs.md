# Telegram batch export (short reference)

## Setup

From the shared `research/` uv project:

```bash
cd research
uv sync --group telegram
cp telegram_scrapper/.env.example telegram_scrapper/.env   # TELEGRAM_API_ID, TELEGRAM_API_HASH, …
```

Install all research deps (RAG + scraper + translate): `uv sync --all-groups`.

## Single chat (`telegram_scrapper.export`)

```bash
cd research
uv run python -m telegram_scrapper.export -1001350470024 --limit 1500 -o telegram_scrapper/my_export.csv
```

- Positional `chat_id`: username, `-100…` id, or `t.me` link.
- `--limit`, `-o`, `--append`, `--tsv`.

## Many chats → one CSV (`telegram_scrapper.batch_export`)

```bash
cd research
uv run python -m telegram_scrapper.batch_export --help
```

- **`chats.json`**: `chats[]` entries include `last_parse_date` (UTC when the job finished that chat), `parsed_messages` (row count written in that run), `oldest_parsed_message_date` and `newest_parsed_message_date` (UTC bounds among **history** rows only; pinned/linked posts are excluded so old pins do not skew `oldest`).
- **`--limit N`**: CLI cap. **Per-chat effective limit:** `min(N, number_of_messages)` when JSON has a per-chat limit; if JSON has none, `N` is used alone.
- **`--since-days D`**: only messages with `date >= now(UTC) - D days`. Startup logs include the **equivalent calendar day** as if you had passed `--until-date YYYY-MM-DD` (UTC).
- **`--until-date YYYY-MM-DD`**: only messages with `date >=` that calendar day at **UTC midnight**.
- If **both** `--since-days` and `--until-date` are set, the **later** instant is used (stricter floor). This combined floor is logged when both are present.
- If **both** a date floor and `--limit` are in effect, iteration stops when **either** condition hits first.
- If none of `--limit`, `--since-days`, `--until-date`, and JSON `number_of_messages` apply, the program exits with an error.
- **`--sleep-between-chats`**: seconds between chats (default `60`).
- **`--sleep-between-messages-number`**: pause every N messages in one chat (default `500`; `0` = off).
- **`--sleep-between-messages-duration`**: pause length in seconds (default `10`).
- If `last_parse_date` is **< 10 days** old, the chat is skipped (logged), unless **`--force-rerun`** is set.
- Errors on one chat are logged; the loop **continues**.
- Merged CSV columns: `text_or_caption`, `msg_id`, `reply_to`, `chat_id`, `date_created`.

## CSV validation (marimo)

```bash
cd research
uv run marimo edit telegram_scrapper/notebooks/csv_readability.py
```

Interactive checks: row count, expected columns, dtypes, nulls, preview.

## Logging

By default **`logging.ini`** is loaded: root gets a **plain** `RotatingFileHandler` on **`telegram_scrapper/logs/log.log`**. **Colored** console output is added separately via **`coloredlogs.install()`** on stdout (same format string as the file handler). Use `NO_COLOR` in the environment to disable ANSI colors.

Custom ini: `--logging-config /path/to.ini`. File handler args: `args=("%(logfile)s",...)` with `logfile` in `defaults`.

**`-v`**: after loading the ini, root and `telegram_scrapper.batch` loggers are set to **DEBUG**.

## Pinned messages

Up to **10** pinned messages are fetched first (`InputMessagesFilterPinned` when available, then fallbacks). If a pin contains **t.me links to posts in the same channel**, those posts are fetched and exported too (hub posts often hold the most relevant info).

## Useful channel

See root `README.md` — [EU_pets](https://t.me/EU_pets).
