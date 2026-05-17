"""Tiny retrieval recall@k smoke test (issue #21 acceptance criterion).

Runs against an in-memory Chroma client seeded with synthetic docs and a
deterministic, topic-based fake embedder — no ollama needed. Exercises the
real search() code path end-to-end (embed -> collection.query -> hit shaping).

Regression coverage on retrieval wiring: if search() stops returning hits,
drops attribution fields, or scrambles ordering, this fails.

A production recall@k eval against the real index belongs in a follow-up
once a labelled QA set exists.
"""

from __future__ import annotations

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


@pytest.fixture
def seeded_collection(monkeypatch):
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.EphemeralClient(
        settings=ChromaSettings(anonymized_telemetry=False)
    )
    coll = client.get_or_create_collection(
        name="eval", metadata={"hnsw:space": "cosine"}
    )
    coll.add(
        ids=[d["doc_id"] for d in DOCS],
        embeddings=[_embed(d["text"]) for d in DOCS],
        documents=[d["text"] for d in DOCS],
        metadatas=[
            {k: d[k] for k in ("chat_id", "kind", "n_msgs", "date_min", "date_max")}
            for d in DOCS
        ],
    )

    monkeypatch.setattr(rag, "_get_collection", lambda: coll)
    monkeypatch.setattr(rag, "embed_text", _embed)
    return coll


class TestRecall:
    def test_recall_at_1_is_perfect_on_synthetic_set(self, seeded_collection):
        correct = 0
        for question, expected in QA_SET:
            hits = rag.search(question, k=1)
            if hits and hits[0]["doc_id"] == expected:
                correct += 1
        assert correct / len(QA_SET) >= 0.8

    def test_recall_at_3_returns_expected_doc_for_every_query(self, seeded_collection):
        for question, expected in QA_SET:
            hits = rag.search(question, k=3)
            assert expected in {
                h["doc_id"] for h in hits
            }, f"query={question!r} expected={expected} got={[h['doc_id'] for h in hits]}"

    def test_hits_carry_source_attribution(self, seeded_collection):
        hits = rag.search("visa question", k=1)
        assert hits[0]["chat_id"] == 1
        assert hits[0]["date_min"].startswith("2026-01-01")
        assert hits[0]["snippet"]
