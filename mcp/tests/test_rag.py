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
            {"text_or_caption": "root q1", "msg_id": 1, "reply_to": None, "chat_id": 100, "date_created": "2026-01-01T10:00:00Z"},
            {"text_or_caption": "reply a1", "msg_id": 2, "reply_to": 1, "chat_id": 100, "date_created": "2026-01-01T10:05:00Z"},
            {"text_or_caption": "follow-up", "msg_id": 3, "reply_to": 2, "chat_id": 100, "date_created": "2026-01-01T10:06:00Z"},
            {"text_or_caption": "standalone msg", "msg_id": 4, "reply_to": None, "chat_id": 100, "date_created": "2026-01-01T11:00:00Z"},
            {"text_or_caption": "other root", "msg_id": 10, "reply_to": None, "chat_id": 200, "date_created": "2026-01-02T09:00:00Z"},
            {"text_or_caption": "other reply", "msg_id": 11, "reply_to": 10, "chat_id": 200, "date_created": "2026-01-02T09:01:00Z"},
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

    def test_thread_doc_concatenates_descendants_in_chronological_order(self, sample_df):
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
                {"text_or_caption": None, "msg_id": 1, "reply_to": None, "chat_id": 1, "date_created": "2026-01-01T00:00:00Z"},
                {"text_or_caption": "real", "msg_id": 2, "reply_to": None, "chat_id": 1, "date_created": "2026-01-01T00:01:00Z"},
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
                {"text_or_caption": "orphan", "msg_id": 99, "reply_to": 50, "chat_id": 7, "date_created": "2026-01-01T00:00:00Z"},
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
            second_kwargs = oc.embed.call_args_list[1].kwargs
            assert len(second_kwargs["input"]) <= rag.settings.RAG_EMBED_FALLBACK_CHAR_LIMIT


class TestSearch:
    def test_returns_hits_with_attribution_and_logs(self, caplog):
        coll = MagicMock()
        coll.query.return_value = {
            "ids": [["thread:1:1", "single:2:5"]],
            "distances": [[0.21, 0.33]],
            "metadatas": [[
                {"chat_id": 1, "kind": "thread", "n_msgs": 3, "date_min": "2026-01-01T00:00:00Z", "date_max": "2026-01-01T00:05:00Z"},
                {"chat_id": 2, "kind": "single", "n_msgs": 1, "date_min": "2026-01-02T00:00:00Z", "date_max": "2026-01-02T00:00:00Z"},
            ]],
            "documents": [["root q1\n---\nreply", "standalone msg"]],
        }
        with patch.object(rag, "_get_collection", return_value=coll), \
             patch.object(rag, "embed_text", return_value=[0.0] * 1024):
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
        assert "0.21" in msgs

    def test_clamps_k_to_max(self):
        coll = MagicMock()
        coll.query.return_value = {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}
        with patch.object(rag, "_get_collection", return_value=coll), \
             patch.object(rag, "embed_text", return_value=[0.0]):
            rag.search("q", k=999)
        called_k = coll.query.call_args.kwargs["n_results"]
        assert called_k == rag.settings.RAG_MAX_K

    def test_empty_query_returns_empty(self):
        with patch.object(rag, "_get_collection") as gc:
            assert rag.search("", k=5) == []
            assert rag.search("   ", k=5) == []
            gc.assert_not_called()


class TestIngest:
    def test_skips_already_ingested_doc_ids(self):
        coll = MagicMock()
        coll.get.return_value = {"ids": ["thread:1:1"]}
        docs = [
            {"doc_id": "thread:1:1", "text": "a", "chat_id": 1, "kind": "thread", "n_msgs": 2, "date_min": "x", "date_max": "y"},
            {"doc_id": "single:1:2", "text": "b", "chat_id": 1, "kind": "single", "n_msgs": 1, "date_min": "x", "date_max": "y"},
        ]
        with patch.object(rag, "embed_texts", return_value=[[0.0]]):
            written = rag.ingest(docs, coll, batch_size=8)
        assert written == 1
        coll.add.assert_called_once()
        added_ids = coll.add.call_args.kwargs["ids"]
        assert added_ids == ["single:1:2"]

    def test_no_new_docs_returns_zero(self):
        coll = MagicMock()
        coll.get.return_value = {"ids": ["a", "b"]}
        docs = [{"doc_id": "a", "text": "x", "chat_id": 1, "kind": "single", "n_msgs": 1, "date_min": "x", "date_max": "y"}]
        with patch.object(rag, "embed_texts") as et:
            written = rag.ingest(docs, coll)
            assert written == 0
            et.assert_not_called()
