"""MCP server configuration. Loaded from environment / .env."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

FIRECRAWL_HARD_MAX_LIMIT = 100


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    MCP_PORT: int = 8001
    BACKEND_URL: str = "http://backend:8000"
    INTERNAL_API_TOKEN: str | None = None
    REQUEST_TIMEOUT_SECONDS: float = 5.0

    # RAG (Telegram chats → pgvector)
    RAG_ENABLED: bool = True
    RAG_DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/postgres"
    RAG_TABLE: str = "rag_threads"
    RAG_EMBED_DIM: int = 1024  # mxbai-embed-large output dim
    OLLAMA_HOST: str = "http://ollama:11434"
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large"
    RAG_DEFAULT_K: int = 5
    RAG_MAX_K: int = 20
    RAG_EMBED_CHAR_LIMIT: int = 600
    RAG_EMBED_FALLBACK_CHAR_LIMIT: int = 300
    RAG_DOC_CHAR_LIMIT: int = 700
    RAG_EMBED_WORKERS: int = 8

    FIRECRAWL_API_KEY: str | None = None
    FIRECRAWL_API_URL: str = "https://api.firecrawl.dev"
    FIRECRAWL_TIMEOUT_SECONDS: float = 30.0
    FIRECRAWL_SEARCH_LIMIT: int = 5

    @field_validator("FIRECRAWL_SEARCH_LIMIT")
    @classmethod
    def _validate_search_limit(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"FIRECRAWL_SEARCH_LIMIT must be >= 1, got {v}")
        if v > FIRECRAWL_HARD_MAX_LIMIT:
            raise ValueError(
                f"FIRECRAWL_SEARCH_LIMIT must be <= {FIRECRAWL_HARD_MAX_LIMIT}, "
                f"got {v}"
            )
        return v

    @field_validator("FIRECRAWL_TIMEOUT_SECONDS")
    @classmethod
    def _validate_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"FIRECRAWL_TIMEOUT_SECONDS must be > 0, got {v}")
        return v


settings = Settings()
