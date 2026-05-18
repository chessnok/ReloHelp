"""Unit tests for the RAG service module (thread building, search, ingest)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app import rag


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Synthetic CSV slice with the new schema: includes msg_id (Valik's update).

    chat 100:
      1 (root)
        2 reply to 1
          3 reply to 2
      4 (root, standalone)
    chat 200:
      10 (root)
        11 reply to 10
    """
    return pd.DataFrame(
        [
            {
                "text_or_caption": "root q1",
                "msg_id": 1,
                "reply_to": None,
                "chat_id": 100,
                "date_created": "2026-01-01T10:00:00Z",
            },
            {
                "text_or_caption": "reply a1",
                "msg_id": 2,
                "reply_to": 1,
                "chat_id": 100,
                "date_created": "2026-01-01T10:05:00Z",
            },
            {
                "text_or_caption": "follow-up",
                "msg_id": 3,
                "reply_to": 2,
                "chat_id": 100,
                "date_created": "2026-01-01T10:06:00Z",
            },
            {
                "text_or_caption": "standalone msg",
                "msg_id": 4,
                "reply_to": None,
                "chat_id": 100,
                "date_created": "2026-01-01T11:00:00Z",
            },
            {
                "text_or_caption": "other root",
                "msg_id": 10,
                "reply_to": None,
                "chat_id": 200,
                "date_created": "2026-01-02T09:00:00Z",
            },
            {
                "text_or_caption": "other reply",
                "msg_id": 11,
                "reply_to": 10,
                "chat_id": 200,
                "date_created": "2026-01-02T09:01:00Z",
            },
        ]
    )


class TestBuildThreads:
    def test_roots_become_thread_docs_with_descendants(self, sample_df):
        docs = rag.build_threads(sample_df)
        thread_ids = {d["doc_id"] for d in docs if d["kind"] == "thread"}
        assert "thread:100:1" in thread_ids
        assert "thread:200:10" in thread_ids

    def test_standalone_root_no_children_is_single(self, sample_df):
        docs = rag.build_threads(sample_df)
        ids = {d["doc_id"] for d in docs}
        assert "single:100:4" in ids
        single = next(d for d in docs if d["doc_id"] == "single:100:4")
        assert single["kind"] == "single"
        assert single["n_msgs"] == 1

    def test_thread_doc_concatenates_descendants_in_chronological_order(
        self, sample_df
    ):
        docs = rag.build_threads(sample_df)
        t = next(d for d in docs if d["doc_id"] == "thread:100:1")
        assert "root q1" in t["text"]
        assert "reply a1" in t["text"]
        assert "follow-up" in t["text"]
        assert t["text"].index("root q1") < t["text"].index("reply a1")
        assert t["text"].index("reply a1") < t["text"].index("follow-up")
        assert t["n_msgs"] == 3

    def test_thread_metadata_carries_chat_id_and_date_bounds(self, sample_df):
        docs = rag.build_threads(sample_df)
        t = next(d for d in docs if d["doc_id"] == "thread:100:1")
        assert t["chat_id"] == 100
        assert t["date_min"] <= t["date_max"]

    def test_drops_rows_with_empty_text(self):
        df = pd.DataFrame(
            [
                {
                    "text_or_caption": None,
                    "msg_id": 1,
                    "reply_to": None,
                    "chat_id": 1,
                    "date_created": "2026-01-01T00:00:00Z",
                },
                {
                    "text_or_caption": "real",
                    "msg_id": 2,
                    "reply_to": None,
                    "chat_id": 1,
                    "date_created": "2026-01-01T00:01:00Z",
                },
            ]
        )
        docs = rag.build_threads(df)
        assert len(docs) == 1
        assert docs[0]["doc_id"] == "single:1:2"

    def test_truncates_text_to_doc_char_limit(self, sample_df):
        docs = rag.build_threads(sample_df, max_chars=10)
        for d in docs:
            assert len(d["text"]) <= 10

    def test_orphan_reply_with_missing_parent_becomes_single(self):
        df = pd.DataFrame(
            [
                {
                    "text_or_caption": "orphan",
                    "msg_id": 99,
                    "reply_to": 50,
                    "chat_id": 7,
                    "date_created": "2026-01-01T00:00:00Z",
                },
            ]
        )
        docs = rag.build_threads(df)
        assert len(docs) == 1
        assert docs[0]["doc_id"] == "single:7:99"
        assert docs[0]["kind"] == "single"


class TestEmbed:
    def test_trims_long_input_and_returns_vector(self):
        fake_resp = {"embeddings": [[0.1] * 1024]}
        with patch.object(rag, "_ollama_client") as oc:
            oc.embed = MagicMock(return_value=fake_resp)
            vec = rag.embed_text("x" * 5000)
            assert len(vec) == 1024
            oc.embed.assert_called_once()
            kwargs = oc.embed.call_args.kwargs
            assert len(kwargs["input"]) <= rag.settings.RAG_EMBED_CHAR_LIMIT

    def test_falls_back_to_shorter_input_on_error(self):
        with patch.object(rag, "_ollama_client") as oc:
            oc.embed = MagicMock(
                side_effect=[RuntimeError("too long"), {"embeddings": [[0.0] * 4]}]
            )
            vec = rag.embed_text("y" * 5000)
            assert vec == [0.0, 0.0, 0.0, 0.0]
            assert oc.embed.call_count == 2

    def test_embed_texts_uses_batched_http_for_one_chunk(self):
        with patch.object(rag.settings, "RAG_EMBED_WORKERS", 8), patch.object(
            rag, "_embed_batch_http", return_value=[[0.1], [0.2]]
        ) as bh:
            out = rag.embed_texts(["a", "b"])
        assert out == [[0.1], [0.2]]
        bh.assert_called_once_with(["a", "b"])

    def test_embed_texts_falls_back_per_item_on_batch_failure(self):
        with patch.object(rag.settings, "RAG_EMBED_WORKERS", 8), patch.object(
            rag, "_embed_batch_http", side_effect=RuntimeError("boom")
        ), patch.object(rag, "embed_text", side_effect=lambda t: [hash(t) % 10]):
            out = rag.embed_texts(["a", "b"])
        assert out == [[hash("a") % 10], [hash("b") % 10]]


class _FakeCursor:
    """Minimal psycopg cursor stub with scripted fetch results per SQL prefix."""

    def __init__(self, scripts):
        self._scripts = scripts
        self._last = None
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        for prefix, rows in self._scripts.items():
            if prefix in sql:
                self._last = rows
                return
        self._last = []

    def executemany(self, sql, rows):
        self.executed.append((sql, list(rows)))

    def fetchall(self):
        return list(self._last or [])


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed += 1


def _patch_pg(rows_for_select_doc_id=None, rows_for_search=None):
    cur = _FakeCursor(
        {
            "SELECT doc_id FROM": [(d,) for d in (rows_for_select_doc_id or [])],
            "ORDER BY embedding": rows_for_search or [],
        }
    )
    conn = _FakeConn(cur)
    return cur, conn


class TestSearch:
    def test_returns_hits_with_attribution_and_logs(self, caplog):
        rows = [
            (
                "thread:1:1",
                1,
                "thread",
                3,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:05:00Z",
                "root q1\n---\nreply",
                0.21,
            ),
            (
                "single:2:5",
                2,
                "single",
                1,
                "2026-01-02T00:00:00Z",
                "2026-01-02T00:00:00Z",
                "standalone msg",
                0.33,
            ),
        ]
        _, conn = _patch_pg(rows_for_search=rows)
        with patch.object(rag, "_ensure_schema"), patch.object(
            rag, "_checkout_conn", return_value=conn
        ), patch.object(rag, "_release"), patch.object(
            rag, "embed_text", return_value=[0.0] * 1024
        ):
            with caplog.at_level("INFO", logger="app.rag"):
                hits = rag.search("how to get visa", k=2)
        assert len(hits) == 2
        assert hits[0]["doc_id"] == "thread:1:1"
        assert hits[0]["distance"] == pytest.approx(0.21)
        assert hits[0]["chat_id"] == 1
        assert hits[0]["snippet"].startswith("root q1")
        msgs = " ".join(r.message for r in caplog.records)
        assert "how to get visa" in msgs
        assert "thread:1:1" in msgs

    def test_clamps_k_to_max(self):
        cur, conn = _patch_pg(rows_for_search=[])
        with patch.object(rag, "_ensure_schema"), patch.object(
            rag, "_checkout_conn", return_value=conn
        ), patch.object(rag, "_release"), patch.object(
            rag, "embed_text", return_value=[0.0]
        ):
            rag.search("q", k=999)
        order_call = next(
            (sql, params) for sql, params in cur.executed if "ORDER BY embedding" in sql
        )
        assert order_call[1][2] == rag.settings.RAG_MAX_K

    def test_empty_query_returns_empty(self):
        with patch.object(rag, "_checkout_conn") as cc:
            assert rag.search("", k=5) == []
            assert rag.search("   ", k=5) == []
            cc.assert_not_called()


class TestIngest:
    def _make_docs(self, ids):
        return [
            {
                "doc_id": i,
                "text": "x",
                "chat_id": 1,
                "kind": "single",
                "n_msgs": 1,
                "date_min": "x",
                "date_max": "y",
            }
            for i in ids
        ]

    def test_skips_already_ingested_doc_ids(self):
        cur, conn = _patch_pg(rows_for_select_doc_id=["thread:1:1"])
        with patch.object(rag, "_ensure_schema"), patch.object(
            rag, "_checkout_conn", return_value=conn
        ), patch.object(rag, "_release"), patch.object(
            rag, "embed_texts", return_value=[[0.0]]
        ):
            written = rag.ingest(
                self._make_docs(["thread:1:1", "single:1:2"]), batch_size=8
            )
        assert written == 1
        many = [c for c in cur.executed if "INSERT INTO" in c[0]]
        assert len(many) == 1
        assert many[0][1][0][0] == "single:1:2"

    def test_no_new_docs_returns_zero(self):
        _, conn = _patch_pg(rows_for_select_doc_id=["a"])
        with patch.object(rag, "_ensure_schema"), patch.object(
            rag, "_checkout_conn", return_value=conn
        ), patch.object(rag, "_release"), patch.object(rag, "embed_texts") as et:
            written = rag.ingest(self._make_docs(["a"]))
            assert written == 0
            et.assert_not_called()


class TestEnsureSchemaRace:
    def test_concurrent_calls_initialize_schema_once(self, monkeypatch):
        import sys
        import threading
        import types

        monkeypatch.setattr(rag, "_schema_initialized", False)
        call_count = {"n": 0}
        block = threading.Event()
        first_in = threading.Event()

        class FakeCur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *_a, **_k):
                return None

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def cursor(self):
                return FakeCur()

            def commit(self):
                return None

        class FakePool:
            def connection(self):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    first_in.set()
                    block.wait(timeout=2)
                return FakeConn()

        monkeypatch.setattr(rag, "_get_pool", lambda: FakePool())
        fake_mod = types.ModuleType("pgvector.psycopg")
        fake_mod.register_vector = lambda *_a, **_k: None  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "pgvector", types.ModuleType("pgvector"))
        monkeypatch.setitem(sys.modules, "pgvector.psycopg", fake_mod)

        results = []

        def worker():
            rag._ensure_schema()
            results.append(True)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        first_in.wait(timeout=2)
        t2.start()
        block.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert len(results) == 2
        assert call_count["n"] == 1
        assert rag._schema_initialized is True
