"""Langfuse client singleton for observability and tracing."""

from typing import Any

from app.core.config import settings
from app.core.logger import logger

_langfuse_client: Any = None


def get_langfuse():
    """Return the Langfuse client singleton, or None if credentials are not configured."""
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.warning(
            "Langfuse credentials not set (LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY). Tracing disabled."
        )
        return None
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        _langfuse_client = client
        return _langfuse_client
    except Exception as e:
        logger.warning("Failed to initialize Langfuse client: %s. Tracing disabled.", e)
        return None
