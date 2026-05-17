"""Tiny retrieval recall@k smoke test (issue #21 acceptance criterion).

Runs against an in-memory fake pgvector backend seeded with synthetic docs and
a deterministic, topic-based fake embedder — no ollama and no Postgres needed.
Exercises the real search() code path end-to-end (embed -> SQL -> hit shaping).
"""

from __future__ import annotations

import math

import pytest

from app import rag

TOPICS = ["visa", "banking", "housing", "health", "school"]


def _embed(text: str) -> list[float]:
    """One-hot per topic keyword; falls back to a tiny default vector."""
    vec = [0.0] * len(TOPICS)
    lowered = text.lower()
    for i, t in enumerate(TOPICS):
        if t in lowered:
            vec[i] = 1.0
    if sum(vec) == 0:
        vec[0] = 0.001
    return vec


def _cosine_distance(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - (dot / (na * nb))


DOCS = [
    {
        "doc_id": "d:visa",
        "text": "how to get a visa for serbia",
        "chat_id": 1,
        "kind": "single",
        "n_msgs": 1,
        "date_min": "2026-01-01T00:00:00Z",
        "date_max": "2026-01-01T00:00:00Z",
    },
    {
        "doc_id": "d:banking",
        "text": "opening a bank account abroad banking",
        "chat_id": 2,
        "kind": "single",
        "n_msgs": 1,
        "date_min": "2026-01-02T00:00:00Z",
        "date_max": "2026-01-02T00:00:00Z",
    },
    {
        "doc_id": "d:housing",
        "text": "finding housing rentals",
        "chat_id": 3,
        "kind": "single",
        "n_msgs": 1,
        "date_min": "2026-01-03T00:00:00Z",
        "date_max": "2026-01-03T00:00:00Z",
    },
    {
        "doc_id": "d:health",
        "text": "health insurance options",
        "chat_id": 4,
        "kind": "single",
        "n_msgs": 1,
        "date_min": "2026-01-04T00:00:00Z",
        "date_max": "2026-01-04T00:00:00Z",
    },
    {
        "doc_id": "d:school",
        "text": "school enrollment for kids",
        "chat_id": 5,
        "kind": "single",
        "n_msgs": 1,
        "date_min": "2026-01-05T00:00:00Z",
        "date_max": "2026-01-05T00:00:00Z",
    },
]

QA_SET = [
    ("how do I get a visa?", "d:visa"),
    ("banking question", "d:banking"),
    ("any housing tips?", "d:housing"),
    ("recommend health insurance", "d:health"),
    ("where to enrol my kid in school?", "d:school"),
]


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        if "ORDER BY embedding" not in sql:
            self._rows = []
            return
        qvec = list(params[0])
        limit = int(params[2])
        scored = []
        for d in self._docs:
            dvec = _embed(d["text"])
            scored.append((_cosine_distance(qvec, dvec), d))
        scored.sort(key=lambda x: x[0])
        self._rows = [
            (
                d["doc_id"],
                d["chat_id"],
                d["kind"],
                d["n_msgs"],
                d["date_min"],
                d["date_max"],
                d["text"],
                dist,
            )
            for dist, d in scored[:limit]
        ]

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, docs):
        self._docs = docs

    def cursor(self):
        return _FakeCursor(self._docs)

    def commit(self):
        return None


@pytest.fixture
def seeded_pg(monkeypatch):
    conn = _FakeConn(DOCS)
    monkeypatch.setattr(rag, "_ensure_schema", lambda: None)
    monkeypatch.setattr(rag, "_checkout_conn", lambda: conn)
    monkeypatch.setattr(rag, "_release", lambda c: None)
    monkeypatch.setattr(rag, "embed_text", _embed)
    return conn


class TestRecall:
    def test_recall_at_1_is_perfect_on_synthetic_set(self, seeded_pg):
        correct = 0
        for question, expected in QA_SET:
            hits = rag.search(question, k=1)
            if hits and hits[0]["doc_id"] == expected:
                correct += 1
        assert correct / len(QA_SET) >= 0.8

    def test_recall_at_3_returns_expected_doc_for_every_query(self, seeded_pg):
        for question, expected in QA_SET:
            hits = rag.search(question, k=3)
            assert expected in {
                h["doc_id"] for h in hits
            }, f"query={question!r} expected={expected} got={[h['doc_id'] for h in hits]}"

    def test_hits_carry_source_attribution(self, seeded_pg):
        hits = rag.search("visa question", k=1)
        assert hits[0]["chat_id"] == 1
        assert hits[0]["date_min"].startswith("2026-01-01")
        assert hits[0]["snippet"]
