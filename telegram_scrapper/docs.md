# Telegram batch export (short reference)

## Single chat (`export.py`)

- Positional `chat_id`: username, `-100…` id, or `t.me` link.
- `--limit`, `-o`, `--append`, `--tsv`.

## Many chats → one CSV (`batch_export.py`)

From the repo root:

```bash
python -m telegram_scrapper.batch_export --help
```

- **`chats.json`**: `chats[]` entries include `last_parse_date` (UTC when the job finished that chat), `parsed_messages` (row count written in that run), `oldest_parsed_message_date` and `newest_parsed_message_date` (UTC bounds among those rows; `null` if none).
- **`--limit N`**: CLI cap. **Per-chat effective limit:** `min(N, number_of_messages)` when JSON has a per-chat limit; if JSON has none, `N` is used alone.
- **`--since-days D`**: only messages with `date >= now(UTC) - D days`. Startup logs include the **equivalent calendar day** as if you had passed `--until-date YYYY-MM-DD` (UTC).
- **`--until-date YYYY-MM-DD`**: only messages with `date >=` that calendar day at **UTC midnight**.
- If **both** `--since-days` and `--until-date` are set, the **later** instant is used (stricter floor). This combined floor is logged when both are present.
- If **both** a date floor and `--limit` are in effect, iteration stops when **either** condition hits first.
- If none of `--limit`, `--since-days`, `--until-date`, and JSON `number_of_messages` apply, the program exits with an error.
- **`--sleep-between-chats`**: seconds between chats (default `60`).
- Inside one chat: pause **10 s** every **500** messages (`export.py`: `INTER_BATCH_MESSAGE_COUNT`, `INTER_BATCH_SLEEP_SEC`).
- If `last_parse_date` is **< 10 days** old, the chat is skipped (logged).
- Errors on one chat are logged; the loop **continues**.

## Logging

By default **`logging.ini`** is loaded: root gets a **plain** `RotatingFileHandler` on **`telegram_scrapper/logs/log.log`**. **Colored** console output is added separately via **`coloredlogs.install()`** on stdout (same format string as the file handler). Use `NO_COLOR` in the environment to disable ANSI colors.

Custom ini: `--logging-config /path/to.ini`. File handler args: `args=("%(logfile)s",...)` with `logfile` in `defaults`.

**`-v`**: after loading the ini, root and `telegram_scrapper.batch` loggers are set to **DEBUG**.

## Pinned messages

Up to **5** pinned messages are requested first (`InputMessagePinned` and `pinned_msg_id` from full channel/chat). Telegram often exposes a **single** “main” pin; multiple independent pins are not always returned as a list.

## Useful channel

See `README.md` — [EU_pets](https://t.me/EU_pets).
