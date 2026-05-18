"""Unit tests for OllamaEmbedder."""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.embeddings import EmbeddingError, OllamaEmbedder


def _ok_handler(dim: int):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        inputs = body["input"]
        return httpx.Response(200, json={"embeddings": [[0.1] * dim for _ in inputs]})

    return handler


def _make_embedder(handler, dim: int = 4) -> OllamaEmbedder:
    transport = httpx.MockTransport(handler)
    embedder = OllamaEmbedder(host="http://x", model="nomic-embed-text", dim=dim)
    embedder._client = httpx.AsyncClient(base_url="http://x", transport=transport)
    return embedder


async def test_embed_one_returns_vector():
    embedder = _make_embedder(_ok_handler(dim=4))
    vec = await embedder.embed_one("hello")
    assert vec == [0.1, 0.1, 0.1, 0.1]
    await embedder.aclose()


async def test_embed_many_batches():
    embedder = _make_embedder(_ok_handler(dim=4))
    vecs = await embedder.embed_many(["a", "b", "c"])
    assert len(vecs) == 3
    assert all(len(v) == 4 for v in vecs)
    await embedder.aclose()


async def test_embed_many_empty_input_short_circuits():
    embedder = _make_embedder(_ok_handler(dim=4))
    assert await embedder.embed_many([]) == []
    await embedder.aclose()


async def test_embed_one_dim_mismatch_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[1.0, 2.0]]})

    embedder = _make_embedder(handler, dim=4)
    with pytest.raises(EmbeddingError):
        await embedder.embed_one("x")
    await embedder.aclose()


async def test_embed_one_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    embedder = _make_embedder(handler, dim=4)
    with pytest.raises(EmbeddingError):
        await embedder.embed_one("x")
    await embedder.aclose()


async def test_normalize_empty_to_space():
    assert OllamaEmbedder._normalize("") == " "
    assert OllamaEmbedder._normalize("   ") == " "
    assert OllamaEmbedder._normalize("hi") == "hi"
