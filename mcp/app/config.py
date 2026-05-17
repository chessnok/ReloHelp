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

    FIRECRAWL_API_KEY: str | None = None
    FIRECRAWL_API_URL: str = "https://api.firecrawl.dev"
    FIRECRAWL_TIMEOUT_SECONDS: float = 30.0
    FIRECRAWL_SEARCH_LIMIT: int = 5


settings = Settings()
