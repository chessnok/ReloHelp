"""Unit tests for MemoryService logic (DB + embedder mocked)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services import memory as memory_mod
from app.services.embeddings import EmbeddingError
from app.services.memory import MemoryHit, MemoryService, _vec_literal


class _StubEmbedder:
    def __init__(self, vec):
        self._vec = vec

    async def embed_one(self, _text: str):
        if isinstance(self._vec, Exception):
            raise self._vec
        return list(self._vec)


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _StubDB:
    def __init__(self, rows_for_query=None):
        self._rows = rows_for_query or []
        self.executed: list[tuple[str, dict]] = []
        self.added: list[object] = []
        self.flushed = False

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params or {}))
        return _StubResult(self._rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        pass


class _NullSessionCtx:
    async def __aenter__(self):
        return _StubDB()

    async def __aexit__(self, *_a):
        return False


class _NullSessionFactory:
    def __call__(self):
        return _NullSessionCtx()


def test_vec_literal_format():
    assert _vec_literal([0.1, 0.2]) == "[0.1000000,0.2000000]"


async def test_search_skips_blank_query():
    svc = MemoryService(embedder=_StubEmbedder([0.0] * 4))
    db = _StubDB()
    assert await svc.search(db, uuid4(), "  ") == []
    assert db.executed == []


async def test_search_returns_filtered_hits():
    rows = [
        SimpleNamespace(
            id=uuid4(),
            kind="fact",
            content="User lives in Lisbon",
            metadata={"src": "extract"},
            similarity=0.91,
        ),
        SimpleNamespace(
            id=uuid4(),
            kind="event",
            content="Booked flight",
            metadata={},
            similarity=0.40,
        ),
    ]
    svc = MemoryService(embedder=_StubEmbedder([0.1, 0.2, 0.3, 0.4]))
    db = _StubDB(rows_for_query=rows)
    hits = await svc.search(db, uuid4(), "where do I live?")
    assert len(hits) == 1
    assert hits[0].kind == "fact"
    assert isinstance(hits[0], MemoryHit)


async def test_search_swallows_embed_error():
    svc = MemoryService(embedder=_StubEmbedder(EmbeddingError("ollama down")))
    db = _StubDB()
    assert await svc.search(db, uuid4(), "q") == []
    assert db.executed == []


async def test_write_rejects_invalid_kind():
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    db = _StubDB()
    assert await svc.write(db, uuid4(), kind="nope", content="x") is None
    assert db.added == []


async def test_write_rejects_empty_content():
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    db = _StubDB()
    assert await svc.write(db, uuid4(), kind="fact", content="   ") is None
    assert db.added == []


async def test_write_swallows_embed_error():
    svc = MemoryService(embedder=_StubEmbedder(EmbeddingError("ollama down")))
    db = _StubDB()
    assert await svc.write(db, uuid4(), kind="fact", content="hi") is None
    assert db.added == []


async def test_write_dedupes_on_high_similarity(monkeypatch):
    monkeypatch.setattr(memory_mod.settings, "MEMORY_DEDUPE_SIMILARITY", 0.95)
    existing_id = uuid4()
    db = _StubDB(rows_for_query=[SimpleNamespace(id=existing_id, similarity=0.99)])
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    out = await svc.write(db, uuid4(), kind="fact", content="duplicate")
    assert out is None
    assert db.added == []
    assert len(db.executed) == 2
    assert "UPDATE memories" in db.executed[1][0]


async def test_write_inserts_when_no_duplicate(monkeypatch):
    monkeypatch.setattr(memory_mod.settings, "MEMORY_DEDUPE_SIMILARITY", 0.95)
    db = _StubDB(rows_for_query=[SimpleNamespace(id=uuid4(), similarity=0.10)])
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    out = await svc.write(db, uuid4(), kind="fact", content="something new")
    assert out is not None
    assert len(db.added) == 1
    assert db.flushed


async def test_extract_and_store_returns_zero_when_disabled(monkeypatch):
    monkeypatch.setattr(memory_mod.settings, "MEMORY_ENABLED", False)
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    assert await svc.extract_and_store(uuid4(), uuid4(), []) == 0


async def test_extract_and_store_handles_extract_failure(monkeypatch):
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    monkeypatch.setattr(
        svc, "_extract", AsyncMock(side_effect=RuntimeError("openai down"))
    )
    assert (
        await svc.extract_and_store(
            uuid4(), uuid4(), [{"role": "user", "content": "x"}]
        )
        == 0
    )


async def test_extract_and_store_drops_invalid_items(monkeypatch):
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    monkeypatch.setattr(
        svc,
        "_extract",
        AsyncMock(
            return_value=[
                {"kind": "garbage", "content": "ignored"},
                {"kind": "fact", "content": ""},
                {"kind": "fact", "content": "User wants Portugal"},
            ]
        ),
    )
    write_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(svc, "write", write_mock)
    monkeypatch.setattr(memory_mod, "AsyncSessionLocal", _NullSessionFactory())
    await svc.extract_and_store(uuid4(), uuid4(), [{"role": "user", "content": "hi"}])
    assert write_mock.await_count == 1
    _args, kwargs = write_mock.await_args
    assert kwargs["kind"] == "fact"
    assert kwargs["content"] == "User wants Portugal"


async def test_extract_parses_json_object(monkeypatch):
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    monkeypatch.setattr(memory_mod.settings, "OPENAI_API_KEY", "sk-test")
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {"items": [{"kind": "fact", "content": "User is fluent in PT"}]}
                    )
                )
            )
        ]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=fake_resp))
        )
    )
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **_kw: fake_client)
    items = await svc._extract(
        [
            {"role": "user", "content": "Hi, I speak Portuguese."},
            {"role": "assistant", "content": "Noted."},
        ]
    )
    assert items == [{"kind": "fact", "content": "User is fluent in PT"}]


async def test_extract_handles_non_json(monkeypatch):
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    monkeypatch.setattr(memory_mod.settings, "OPENAI_API_KEY", "sk-test")
    fake_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=fake_resp))
        )
    )
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **_kw: fake_client)
    assert await svc._extract([{"role": "user", "content": "x"}]) == []


async def test_extract_skips_when_no_openai_key(monkeypatch):
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    monkeypatch.setattr(memory_mod.settings, "OPENAI_API_KEY", None)
    assert await svc._extract([{"role": "user", "content": "x"}]) == []


async def test_extract_skips_when_no_usable_turns(monkeypatch):
    svc = MemoryService(embedder=_StubEmbedder([0.1] * 4))
    monkeypatch.setattr(memory_mod.settings, "OPENAI_API_KEY", "sk-test")
    assert await svc._extract([{"role": "tool", "content": "x"}]) == []
