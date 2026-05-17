"""RAG service: Telegram chats → ChromaDB.

Ported from the research notebook (`research/rag_pipeline.py`, PR #22).

Schema assumed for source CSV (per Valik on PR #22):
    text_or_caption, msg_id, reply_to, chat_id, date_created

Pipeline:
  1. Reconstruct threads using `msg_id` ↔ `reply_to` parent chain.
     Each root = (chat_id, msg_id) with no parent or whose parent is absent.
     Root + descendants (BFS, chronological) = one "thread" doc.
     Root with no descendants = one "single" doc.
  2. Embed via ollama (model from settings).
  3. Persist in ChromaDB (cosine). Incremental: skips already-ingested doc_ids.
  4. search(query, k) returns top-k hits with source attribution
     (chat_id, kind, date_min, date_max, snippet).

Observability: query, top-k ids, and distances are logged on every search.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger("app.rag")

_ollama_client: Any = None
_chroma_client: Any = None
_collection: Any = None


def _get_ollama():
    global _ollama_client
    if _ollama_client is None:
        import ollama

        _ollama_client = ollama.Client(host=settings.OLLAMA_HOST)
    return _ollama_client


def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        Path(settings.CHROMA_DIR).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _collection = _chroma_client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


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


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [embed_text(t) for t in texts]


def build_threads(df, max_chars: int | None = None) -> list[dict[str, Any]]:
    """Build thread docs from a DataFrame of Telegram messages.

    Returns list of dicts with keys:
        doc_id, text, chat_id, kind, n_msgs, date_min, date_max.
    """
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


def ingest(
    docs: list[dict[str, Any]],
    collection: Any = None,
    batch_size: int = 32,
) -> int:
    """Incrementally upsert docs into the collection. Returns count written."""
    coll = collection if collection is not None else _get_collection()
    if not docs:
        return 0

    existing_ids: set[str] = set(coll.get(ids=[d["doc_id"] for d in docs])["ids"])
    todo = [d for d in docs if d["doc_id"] not in existing_ids]
    if not todo:
        return 0

    written = 0
    for start in range(0, len(todo), batch_size):
        chunk = todo[start : start + batch_size]
        texts = [d["text"] for d in chunk]
        embs = embed_texts(texts)
        metas = [
            {
                "chat_id": d["chat_id"],
                "kind": d["kind"],
                "n_msgs": d["n_msgs"],
                "date_min": d["date_min"],
                "date_max": d["date_max"],
            }
            for d in chunk
        ]
        coll.add(
            ids=[d["doc_id"] for d in chunk],
            embeddings=embs,
            documents=texts,
            metadatas=metas,
        )
        written += len(chunk)
    logger.info("rag.ingest wrote %d new docs", written)
    return written


def search(query: str, k: int = 5, snippet_chars: int = 300) -> list[dict[str, Any]]:
    """Top-k semantic search. Returns hits with source attribution.

    Each hit: {doc_id, distance, chat_id, kind, n_msgs, date_min, date_max, snippet}.
    """
    if not query or not query.strip():
        return []
    k_clamped = max(1, min(int(k), settings.RAG_MAX_K))
    coll = _get_collection()
    qvec = embed_text(query)
    res = coll.query(query_embeddings=[qvec], n_results=k_clamped)

    ids = (res.get("ids") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]
    metadatas = (res.get("metadatas") or [[]])[0]
    documents = (res.get("documents") or [[]])[0]

    hits: list[dict[str, Any]] = []
    for i, doc_id in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) else {}
        hits.append(
            {
                "doc_id": doc_id,
                "distance": float(distances[i]) if i < len(distances) else None,
                "chat_id": meta.get("chat_id"),
                "kind": meta.get("kind"),
                "n_msgs": meta.get("n_msgs"),
                "date_min": meta.get("date_min"),
                "date_max": meta.get("date_max"),
                "snippet": (documents[i] or "")[:snippet_chars] if i < len(documents) else "",
            }
        )

    logger.info(
        "rag.search query=%r k=%d ids=%s distances=%s",
        query,
        k_clamped,
        [h["doc_id"] for h in hits],
        [round(h["distance"], 4) if h["distance"] is not None else None for h in hits],
    )
    return hits
