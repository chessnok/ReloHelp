"""Async Ollama embedding client.

Mirrors the request shape used by mcp/app/rag.py (POST /api/embed with
{model, input, truncate=true}) but async-native so it can be called from
the FastAPI event loop without thread offload.
"""

from __future__ import annotations

import asyncio
from typing import Sequence

import httpx

from app.core.config import settings
from app.core.logger import logger


class EmbeddingError(RuntimeError):
    """Raised when Ollama cannot produce a usable embedding."""


class OllamaEmbedder:
    def __init__(
        self,
        host: str,
        model: str,
        dim: int,
        timeout: float = 30.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._dim = dim
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        base_url=self._host, timeout=self._timeout
                    )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed_many([text])
        return vectors[0]

    async def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned = [self._normalize(t) for t in texts]
        try:
            return await self._call(cleaned)
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001 — fallback path
            logger.warning("Ollama batch embed failed, falling back per-item: %s", exc)
            results: list[list[float]] = []
            for t in cleaned:
                results.append((await self._call([t]))[0])
            return results

    async def _call(self, inputs: list[str]) -> list[list[float]]:
        client = await self._get_client()
        try:
            response = await client.post(
                "/api/embed",
                json={
                    "model": self._model,
                    "input": inputs,
                    "truncate": True,
                },
            )
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Ollama request failed: {exc}") from exc

        if response.status_code != 200:
            raise EmbeddingError(
                f"Ollama returned {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        vectors = payload.get("embeddings") or []
        if not vectors:
            raise EmbeddingError(f"Ollama returned no embeddings: {payload}")
        for v in vectors:
            if not isinstance(v, list) or len(v) != self._dim:
                got = len(v) if isinstance(v, list) else "?"
                raise EmbeddingError(
                    f"Ollama returned vector of dim {got}, expected {self._dim}"
                )
        return [list(map(float, v)) for v in vectors]

    @staticmethod
    def _normalize(text: str) -> str:
        if not text:
            return " "
        return text.strip() or " "


_embedder: OllamaEmbedder | None = None


def get_embedder() -> OllamaEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbedder(
            host=settings.OLLAMA_HOST,
            model=settings.MEMORY_EMBED_MODEL,
            dim=settings.MEMORY_EMBED_DIM,
        )
    return _embedder


async def shutdown_embedder() -> None:
    global _embedder
    if _embedder is not None:
        await _embedder.aclose()
        _embedder = None
