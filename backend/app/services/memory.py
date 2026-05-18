"""Per-user long-term memory: extract, embed, store, retrieve."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.db.models.memory import Memory
from app.db.session import AsyncSessionLocal
from app.services.embeddings import EmbeddingError, OllamaEmbedder, get_embedder

_VALID_KINDS = frozenset({"fact", "preference", "event", "summary"})

_EXTRACTION_SYSTEM_PROMPT = (
    "You extract durable, user-specific facts from a relocation-assistant chat. "
    "Return ONLY a JSON object of the shape: "
    '{"items": [{"kind": "fact|preference|event|summary", "content": "..."}]}. '
    "Capture: current/target country, profession, family composition, deadlines, "
    "budget, language, visa type, prior steps taken. Skip greetings, chit-chat, "
    "and anything the assistant said about itself. Use third person about the "
    "user ('User is moving to Portugal in March 2026'). Return "
    '{"items": []} if nothing is memorable.'
)


@dataclass(frozen=True)
class MemoryHit:
    id: UUID
    kind: str
    content: str
    similarity: float
    metadata: dict[str, Any]


class MemoryService:
    def __init__(self, embedder: OllamaEmbedder | None = None) -> None:
        self._embedder = embedder or get_embedder()

    async def search(
        self,
        db: AsyncSession,
        user_id: UUID,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[MemoryHit]:
        if not query.strip():
            return []
        k = top_k or settings.MEMORY_TOP_K
        thr = threshold if threshold is not None else settings.MEMORY_MIN_SIMILARITY
        try:
            qvec = await self._embedder.embed_one(query)
        except EmbeddingError as exc:
            logger.warning("Memory search skipped — embed failed: %s", exc)
            return []

        rows = await db.execute(
            text(
                """
                SELECT id, kind, content, metadata,
                       1 - (embedding <=> CAST(:q AS vector)) AS similarity
                FROM memories
                WHERE user_id = :uid
                ORDER BY embedding <=> CAST(:q AS vector)
                LIMIT :k
                """
            ),
            {"q": _vec_literal(qvec), "uid": str(user_id), "k": k},
        )
        out: list[MemoryHit] = []
        for r in rows:
            similarity = float(r.similarity)
            if similarity < thr:
                continue
            out.append(
                MemoryHit(
                    id=r.id,
                    kind=r.kind,
                    content=r.content,
                    similarity=similarity,
                    metadata=r.metadata or {},
                )
            )
        return out

    async def write(
        self,
        db: AsyncSession,
        user_id: UUID,
        kind: str,
        content: str,
        conversation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Memory | None:
        if kind not in _VALID_KINDS:
            logger.warning("Refusing memory with invalid kind %r", kind)
            return None
        content = content.strip()
        if not content:
            return None

        try:
            vec = await self._embedder.embed_one(content)
        except EmbeddingError as exc:
            logger.warning("Memory write skipped — embed failed: %s", exc)
            return None

        dupe = await db.execute(
            text(
                """
                SELECT id, 1 - (embedding <=> CAST(:q AS vector)) AS similarity
                FROM memories
                WHERE user_id = :uid AND kind = :kind
                ORDER BY embedding <=> CAST(:q AS vector)
                LIMIT 1
                """
            ),
            {
                "q": _vec_literal(vec),
                "uid": str(user_id),
                "kind": kind,
            },
        )
        row = dupe.first()
        if (
            row is not None
            and float(row.similarity) >= settings.MEMORY_DEDUPE_SIMILARITY
        ):
            await db.execute(
                text("UPDATE memories SET updated_at = now() WHERE id = :id"),
                {"id": row.id},
            )
            return None

        mem = Memory(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation_id,
            kind=kind,
            content=content,
            embedding=vec,
            meta=metadata or {},
        )
        db.add(mem)
        await db.flush()
        return mem

    async def extract_and_store(
        self,
        user_id: UUID,
        conversation_id: UUID,
        recent_turns: Sequence[dict[str, Any]],
    ) -> int:
        if not settings.MEMORY_ENABLED:
            return 0
        try:
            items = await self._extract(recent_turns)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Memory extraction LLM call failed: %s", exc)
            return 0
        if not items:
            return 0

        written = 0
        async with AsyncSessionLocal() as db:
            for item in items:
                kind = (item.get("kind") or "").strip().lower()
                content = (item.get("content") or "").strip()
                if not content or kind not in _VALID_KINDS:
                    continue
                mem = await self.write(
                    db,
                    user_id=user_id,
                    kind=kind,
                    content=content,
                    conversation_id=conversation_id,
                )
                if mem is not None:
                    written += 1
            await db.commit()
        if written:
            logger.info(
                "Stored %s new memories for user %s (conversation %s)",
                written,
                user_id,
                conversation_id,
            )
        return written

    async def _extract(
        self, recent_turns: Sequence[dict[str, Any]]
    ) -> list[dict[str, str]]:
        from openai import AsyncOpenAI

        if not settings.OPENAI_API_KEY:
            return []
        usable = [
            t
            for t in recent_turns
            if t.get("role") in {"user", "assistant"} and t.get("content")
        ]
        if not usable:
            return []
        transcript = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in usable)

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        model = settings.MEMORY_EXTRACTION_MODEL or settings.OPENAI_MODEL
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Memory extractor returned non-JSON: %s", raw[:200])
            return []
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [i for i in items if isinstance(i, dict)]


def _vec_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.7f}" for x in vec) + "]"


_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    global _service
    if _service is None:
        _service = MemoryService()
    return _service
