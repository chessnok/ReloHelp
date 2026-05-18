"""RAG service: Telegram chats → Postgres + pgvector.

Pipeline:
  1. Reconstruct threads using `msg_id` ↔ `reply_to` parent chain (build_threads).
  2. Embed via ollama (parallel HTTP requests; ollama serves
     OLLAMA_NUM_PARALLEL concurrent inferences).
  3. Persist in Postgres table `rag_threads` (pgvector cosine).
     Incremental: ON CONFLICT (doc_id) DO NOTHING.
  4. search(query, k) returns top-k via `embedding <=> qvec` (cosine distance).

CSV schema:
    text_or_caption, msg_id, reply_to, chat_id, date_created
"""

from __future__ import annotations

import atexit
import logging
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.config import settings

logger = logging.getLogger("app.rag")

_ollama_client: Any = None
_pool: Any = None
_schema_initialized: bool = False
_schema_lock = threading.Lock()


def _get_ollama():
    global _ollama_client
    if _ollama_client is None:
        import ollama

        _ollama_client = ollama.Client(host=settings.OLLAMA_HOST)
    return _ollama_client


def _get_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(
            conninfo=settings.RAG_DATABASE_URL,
            min_size=1,
            max_size=max(4, settings.RAG_EMBED_WORKERS),
            kwargs={"autocommit": False},
        )
        atexit.register(_close_pool)
    return _pool


def _close_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None


def _ensure_schema() -> None:
    global _schema_initialized
    if _schema_initialized:
        return
    with _schema_lock:
        if _schema_initialized:
            return
        from pgvector.psycopg import register_vector

        pool = _get_pool()
        table = settings.RAG_TABLE
        dim = int(settings.RAG_EMBED_DIM)
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        doc_id     text PRIMARY KEY,
                        chat_id    bigint,
                        kind       text,
                        n_msgs     integer,
                        date_min   text,
                        date_max   text,
                        snippet    text,
                        embedding  vector({dim})
                    );
                    """)
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS {table}_embedding_idx "
                    f"ON {table} USING hnsw (embedding vector_cosine_ops);"
                )
            conn.commit()
        _schema_initialized = True


def _checkout_conn():
    from pgvector.psycopg import register_vector

    pool = _get_pool()
    conn = pool.getconn()
    register_vector(conn)
    return conn


def _release(conn) -> None:
    _get_pool().putconn(conn)


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit]


def embed_text(text: str) -> list[float]:
    """Embed a single string. Falls back to a shorter trim on ollama error."""
    client = _ollama_client if _ollama_client is not None else _get_ollama()
    trimmed = _trim(text, settings.RAG_EMBED_CHAR_LIMIT)
    try:
        resp = client.embed(
            model=settings.OLLAMA_EMBED_MODEL, input=trimmed, truncate=True
        )
        return resp["embeddings"][0]
    except Exception as exc:
        logger.warning(
            "ollama.embed failed (len=%d): %s; retrying with shorter input",
            len(trimmed),
            exc,
        )
        shorter = _trim(text, settings.RAG_EMBED_FALLBACK_CHAR_LIMIT)
        resp = client.embed(
            model=settings.OLLAMA_EMBED_MODEL, input=shorter, truncate=True
        )
        return resp["embeddings"][0]


def _embed_batch_http(texts: list[str]) -> list[list[float]]:
    """Single ollama HTTP call with list input. Server batches internally."""
    client = _ollama_client if _ollama_client is not None else _get_ollama()
    trimmed = [_trim(t, settings.RAG_EMBED_CHAR_LIMIT) for t in texts]
    resp = client.embed(model=settings.OLLAMA_EMBED_MODEL, input=trimmed, truncate=True)
    return resp["embeddings"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed many texts. Splits into sub-batches sent in parallel HTTP calls.

    Each sub-batch is a single ollama request with list input (server-side
    batching). Sub-batches are dispatched concurrently via ThreadPoolExecutor
    so ollama's OLLAMA_NUM_PARALLEL slots stay busy.
    """
    if not texts:
        return []
    workers = max(1, settings.RAG_EMBED_WORKERS)
    # Single HTTP call when the whole batch fits one worker. Otherwise split
    # into exactly `workers` chunks dispatched in parallel.
    if len(texts) <= workers:
        chunks = [list(texts)]
    else:
        sub = (len(texts) + workers - 1) // workers
        chunks = [texts[i : i + sub] for i in range(0, len(texts), sub)]

    if len(chunks) == 1:
        try:
            return _embed_batch_http(chunks[0])
        except Exception as exc:
            logger.warning("batch embed failed (%s); falling back per-item", exc)
            return [embed_text(t) for t in chunks[0]]

    def _safe(chunk: list[str]) -> list[list[float]]:
        try:
            return _embed_batch_http(chunk)
        except Exception as exc:
            logger.warning("batch embed failed (%s); per-item fallback", exc)
            return [embed_text(t) for t in chunk]

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        results = list(pool.map(_safe, chunks))
    out: list[list[float]] = []
    for r in results:
        out.extend(r)
    return out


def build_threads(df, max_chars: int | None = None) -> list[dict[str, Any]]:
    """Build thread docs from a DataFrame of Telegram messages."""
    import pandas as pd

    limit = max_chars if max_chars is not None else settings.RAG_DOC_CHAR_LIMIT
    df = df.dropna(subset=["text_or_caption"]).copy()
    if df.empty:
        return []

    df["msg_id"] = pd.to_numeric(df["msg_id"], errors="coerce").astype("Int64")
    df["reply_to"] = pd.to_numeric(df["reply_to"], errors="coerce").astype("Int64")
    df["chat_id"] = pd.to_numeric(df["chat_id"], errors="coerce").astype("Int64")
    df["date_created"] = pd.to_datetime(df["date_created"], utc=True, errors="coerce")
    df = df.dropna(subset=["msg_id", "chat_id"])
    df = df.sort_values(["chat_id", "date_created", "msg_id"]).reset_index(drop=True)

    docs: list[dict[str, Any]] = []

    for chat_id, group in df.groupby("chat_id", sort=False):
        present_ids: set[int] = {int(x) for x in group["msg_id"].tolist()}
        children: dict[int, list[int]] = defaultdict(list)
        rows_by_id: dict[int, dict[str, Any]] = {}

        for r in group.itertuples(index=False):
            mid = int(r.msg_id)
            rows_by_id[mid] = {"text": str(r.text_or_caption), "date": r.date_created}
            parent = r.reply_to
            if pd.notna(parent) and int(parent) in present_ids:
                children[int(parent)].append(mid)

        roots: list[int] = []
        for r in group.itertuples(index=False):
            mid = int(r.msg_id)
            parent = r.reply_to
            if pd.isna(parent) or int(parent) not in present_ids:
                roots.append(mid)

        for root in roots:
            visited: set[int] = set()
            order: list[int] = []
            queue: deque[int] = deque([root])
            while queue:
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)
                order.append(current)
                for child in sorted(
                    children.get(current, []),
                    key=lambda x: (rows_by_id[x]["date"], x),
                ):
                    queue.append(child)

            ordered = sorted(order, key=lambda x: (rows_by_id[x]["date"], x))
            texts = [rows_by_id[m]["text"] for m in ordered]
            dates = [rows_by_id[m]["date"] for m in ordered]
            n = len(ordered)
            kind = "thread" if n > 1 else "single"
            doc_id = f"{kind}:{int(chat_id)}:{root}"
            joined = "\n---\n".join(texts) if n > 1 else texts[0]
            docs.append(
                {
                    "doc_id": doc_id,
                    "text": _trim(joined, limit),
                    "chat_id": int(chat_id),
                    "kind": kind,
                    "n_msgs": n,
                    "date_min": str(min(dates)),
                    "date_max": str(max(dates)),
                }
            )

    return docs


def _existing_ids(conn, doc_ids: list[str]) -> set[str]:
    table = settings.RAG_TABLE
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT doc_id FROM {table} WHERE doc_id = ANY(%s)",
            (doc_ids,),
        )
        return {row[0] for row in cur.fetchall()}


def ingest(docs: list[dict[str, Any]], batch_size: int = 32) -> int:
    """Incremental upsert. Returns count newly written."""
    if not docs:
        return 0

    _ensure_schema()
    table = settings.RAG_TABLE

    conn = _checkout_conn()
    try:
        existing = _existing_ids(conn, [d["doc_id"] for d in docs])
    finally:
        _release(conn)

    todo = [d for d in docs if d["doc_id"] not in existing]
    if not todo:
        return 0

    written = 0
    for start in range(0, len(todo), batch_size):
        chunk = todo[start : start + batch_size]
        texts = [d["text"] for d in chunk]
        embs = embed_texts(texts)
        rows = [
            (
                d["doc_id"],
                d["chat_id"],
                d["kind"],
                d["n_msgs"],
                d["date_min"],
                d["date_max"],
                d["text"],
                emb,
            )
            for d, emb in zip(chunk, embs)
        ]
        conn = _checkout_conn()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    f"""
                    INSERT INTO {table}
                        (doc_id, chat_id, kind, n_msgs, date_min, date_max, snippet, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (doc_id) DO NOTHING
                    """,
                    rows,
                )
            conn.commit()
        finally:
            _release(conn)
        written += len(chunk)
    logger.info("rag.ingest wrote %d new docs", written)
    return written


def search(query: str, k: int = 5, snippet_chars: int = 300) -> list[dict[str, Any]]:
    """Top-k semantic search via pgvector cosine distance.

    Hit: {doc_id, distance, chat_id, kind, n_msgs, date_min, date_max, snippet}.
    """
    if not query or not query.strip():
        return []
    k_clamped = max(1, min(int(k), settings.RAG_MAX_K))
    _ensure_schema()
    qvec = embed_text(query)
    table = settings.RAG_TABLE

    conn = _checkout_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT doc_id, chat_id, kind, n_msgs, date_min, date_max, snippet,
                       embedding <=> %s::vector AS distance
                FROM {table}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (qvec, qvec, k_clamped),
            )
            rows = cur.fetchall()
    finally:
        _release(conn)

    hits: list[dict[str, Any]] = [
        {
            "doc_id": r[0],
            "distance": float(r[7]) if r[7] is not None else None,
            "chat_id": r[1],
            "kind": r[2],
            "n_msgs": r[3],
            "date_min": r[4],
            "date_max": r[5],
            "snippet": (r[6] or "")[:snippet_chars],
        }
        for r in rows
    ]

    logger.info(
        "rag.search query=%r k=%d ids=%s distances=%s",
        query,
        k_clamped,
        [h["doc_id"] for h in hits],
        [round(h["distance"], 4) if h["distance"] is not None else None for h in hits],
    )
    return hits
