"""MCP server configuration. Loaded from environment / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    MCP_PORT: int = 8001
    BACKEND_URL: str = "http://backend:8000"
    INTERNAL_API_TOKEN: str | None = None
    REQUEST_TIMEOUT_SECONDS: float = 5.0

    # RAG (Telegram chats → ChromaDB)
    RAG_ENABLED: bool = True
    CHROMA_DIR: str = "/data/chroma"
    CHROMA_COLLECTION: str = "tg_threads"
    OLLAMA_HOST: str = "http://ollama:11434"
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large"
    RAG_DEFAULT_K: int = 5
    RAG_MAX_K: int = 20
    RAG_EMBED_CHAR_LIMIT: int = 600
    RAG_EMBED_FALLBACK_CHAR_LIMIT: int = 300
    RAG_DOC_CHAR_LIMIT: int = 700


settings = Settings()
