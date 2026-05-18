"""FastMCP server exposing tools for the AI agent.

Tools do NOT touch the database directly. They talk to the backend over HTTP
using a shared INTERNAL_API_TOKEN.
"""

import asyncio
import logging
from uuid import UUID

import httpx
from fastmcp import FastMCP

from app import rag
from app.config import FIRECRAWL_HARD_MAX_LIMIT, settings

logger = logging.getLogger("app.server")

SYSTEM_INSTRUCTIONS = """\
You are the Relohelp relocation assistant.

Source-of-truth policy (MANDATORY):
- Rely ONLY on NEW and OFFICIAL data when answering questions about visas,
  taxes, prices, regulations, residency, healthcare, or any other
  jurisdiction-specific topic.
- "Official" means: government portals (.gov, .gob, .gouv, ministry sites),
  embassies/consulates, official municipal/regional authorities, primary
  providers (carriers, banks, insurers) on their own domains, and
  authoritative international bodies (EU, UN, OECD, WHO).
- "New" means: prefer content updated within the last 12 months. Discard
  anything stale, undated, or contradicting a more recent official source.
- NEVER answer from training-cutoff memory for time-sensitive facts. Call
  `find_official_info` first for jurisdiction-specific facts.
- For real-world community experience (visa application stories, banking,
  paperwork tips), ALSO call `search_telegram_chats` and cite chat_id +
  date_min/date_max for each snippet you use.
- If no official, recent source is found, say so explicitly and refuse to
  guess.
- Always cite the source URL and its published/updated date when available.
"""

mcp = FastMCP("Relohelp MCP Server", instructions=SYSTEM_INSTRUCTIONS)


def _internal_headers() -> dict[str, str]:
    if not settings.INTERNAL_API_TOKEN:
        return {}
    return {"X-Internal-Token": settings.INTERNAL_API_TOKEN}


@mcp.tool
async def get_user_email(user_id: str) -> dict:
    """Returns the authenticated user's email.

    Args:
        user_id: The UUID of the user whose email to retrieve.
    """
    try:
        UUID(user_id)
    except ValueError:
        return {"email": "", "error": "Invalid user_id format"}

    url = f"{settings.BACKEND_URL.rstrip('/')}/api/v1/internal/users/{user_id}/email"
    try:
        async with httpx.AsyncClient(
            timeout=settings.REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(url, headers=_internal_headers())
    except httpx.HTTPError as exc:
        return {"email": "", "error": f"Backend unreachable: {exc}"}

    if response.status_code == 404:
        return {"email": "", "error": "User not found"}
    if response.status_code == 401:
        return {"email": "", "error": "Unauthorized (internal token invalid)"}
    if response.status_code >= 400:
        return {"email": "", "error": f"Backend error: {response.status_code}"}

    try:
        data = response.json()
    except ValueError:
        return {"email": "", "error": "Invalid backend response"}

    return {"email": data.get("email", "")}


@mcp.tool
async def search_telegram_chats(query: str, k: int = 5) -> dict:
    """Retrieves relevant snippets from indexed Telegram relocation/visa chats.

    Use this when the user asks about real-world relocation, visa, residence permit,
    legalization, or other migration questions where on-the-ground community advice
    helps. Each hit includes `chat_id` and `date_min`/`date_max` for attribution —
    cite these in your reply.

    Args:
        query: Natural-language question (any language; Russian or English work).
        k: Number of hits to return (1..20).

    Returns:
        {"hits": [{doc_id, distance, chat_id, kind, n_msgs, date_min, date_max, snippet}, ...]}
        or {"hits": [], "error": "..."} if RAG is disabled / unavailable.
    """
    if not settings.RAG_ENABLED:
        return {"hits": [], "error": "RAG retrieval is disabled"}
    if not isinstance(query, str) or not query.strip():
        return {"hits": [], "error": "Empty query"}
    try:
        k_int = int(k)
    except (TypeError, ValueError):
        return {"hits": [], "error": "Invalid k"}
    k_clamped = max(1, min(k_int, settings.RAG_MAX_K))
    try:
        hits = await asyncio.to_thread(rag.search, query, k=k_clamped)
    except Exception as exc:
        logger.exception("rag.search failed: %s", exc)
        return {"hits": [], "error": "Retrieval failed"}
    return {"hits": hits}


@mcp.tool
async def find_official_info(query: str, limit: int | None = None) -> dict:
    """Search the public web via Firecrawl for fresh, official information.

    Use this tool whenever you need authoritative, up-to-date facts that may
    have changed since training (visa rules, tax rates, prices, regulations,
    embassy procedures, official forms). Always prefer results from
    government, embassy, or primary-provider domains. Discard anything stale
    or unofficial.

    Args:
        query: Natural-language search query. Be specific and include the
            country/jurisdiction. Example: "Portugal D7 visa minimum income
            requirement 2026 official".
        limit: Max results to return (default from FIRECRAWL_SEARCH_LIMIT).

    Returns:
        {"results": [{"url", "title", "description", "markdown"}, ...]} on
        success, or {"results": [], "error": "..."} on failure.
    """
    if not query or not query.strip():
        return {"results": [], "error": "Query is empty"}

    if not settings.FIRECRAWL_API_KEY:
        return {
            "results": [],
            "error": "Firecrawl is not configured (FIRECRAWL_API_KEY missing)",
        }

    settings_cap = min(settings.FIRECRAWL_SEARCH_LIMIT, FIRECRAWL_HARD_MAX_LIMIT)
    if isinstance(limit, int) and limit > 0:
        effective_limit = min(limit, settings_cap)
    else:
        effective_limit = settings_cap

    url = f"{settings.FIRECRAWL_API_URL.rstrip('/')}/v1/search"
    payload = {
        "query": query.strip(),
        "limit": effective_limit,
        "scrapeOptions": {"formats": ["markdown"]},
    }
    headers = {
        "Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.FIRECRAWL_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        return {"results": [], "error": f"Firecrawl unreachable: {exc}"}

    if response.status_code == 401:
        return {"results": [], "error": "Firecrawl unauthorized (bad API key)"}
    if response.status_code == 402:
        return {"results": [], "error": "Firecrawl quota exhausted"}
    if response.status_code == 429:
        return {"results": [], "error": "Firecrawl rate-limited"}
    if response.status_code >= 400:
        return {
            "results": [],
            "error": f"Firecrawl error: {response.status_code}",
        }

    try:
        body = response.json()
    except ValueError:
        return {"results": [], "error": "Invalid Firecrawl response"}

    if isinstance(body, dict) and body.get("success") is False:
        err_msg = body.get("error") or body.get("message") or "unknown error"
        return {"results": [], "error": f"Firecrawl returned failure: {err_msg}"}

    raw_results = _extract_search_items(body)
    normalized = [
        _normalize_search_item(item) for item in raw_results if isinstance(item, dict)
    ]

    return {"results": normalized}


def _extract_search_items(body: dict) -> list:
    """Normalize v1 (flat) and v2 (nested data['web']) Firecrawl payloads."""
    data = body.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # v2 shape: data = {"web": [...], "news": [...], ...}
        merged: list = []
        for value in data.values():
            if isinstance(value, list):
                merged.extend(value)
        if merged:
            return merged
    results = body.get("results")
    if isinstance(results, list):
        return results
    return []


def _normalize_search_item(item: dict) -> dict:
    raw_metadata = item.get("metadata")
    metadata: dict = raw_metadata if isinstance(raw_metadata, dict) else {}
    published = (
        item.get("publishedDate")
        or item.get("published_date")
        or metadata.get("publishedDate")
        or metadata.get("published_date")
        or metadata.get("article:published_time")
        or ""
    )
    updated = (
        item.get("updatedDate")
        or item.get("updated_date")
        or metadata.get("updatedDate")
        or metadata.get("updated_date")
        or metadata.get("article:modified_time")
        or ""
    )
    return {
        "url": item.get("url", ""),
        "title": item.get("title", "") or metadata.get("title", ""),
        "description": item.get("description", "") or metadata.get("description", ""),
        "markdown": item.get("markdown", ""),
        "publishedDate": published,
        "updatedDate": updated,
    }
