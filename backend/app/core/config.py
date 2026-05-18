from typing import Annotated, List

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "FastAPI Base App"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ALLOWED_ORIGINS: Annotated[List[str], NoDecode] = ["*"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, v):
        """Accept comma-separated string or single "*" in addition to JSON list."""
        if v is None or v == "":
            return ["*"]
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                import json

                return json.loads(s)
            return [item.strip() for item in s.split(",") if item.strip()]
        return v

    # Database settings
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "postgres"

    # S3 settings (MinIO)
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_PUBLIC_URL: str = Field(
        "http://localhost:9000",
        description="Public URL for MinIO (used in pre-signed URLs)",
    )
    S3_ACCESS_KEY_ID: str = "minioadmin"
    S3_SECRET_ACCESS_KEY: str = "minioadmin"
    S3_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "default-bucket"
    S3_USE_SSL: bool = False

    # Redis settings
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    CSRF_SECRET_KEY: str = "secret"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_ALGORITHM: str = "HS256"
    JWT_SECRET_KEY: str = "secret"
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 60 * 24 * 30
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 24 * 7
    RATE_LIMIT_LOGIN_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 60
    RATE_LIMIT_ENABLED: bool = False  # Set True and add Redis for production
    COOKIE_SECURE: bool = False
    COOKIE_SAME_SITE: str = "lax"
    COOKIE_DOMAIN: str | None = "localhost"
    # Email settings
    EMAIL_PROVIDER: str = "resend"  # "smtp" or "resend"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_TLS: bool = True
    RESEND_API_KEY: str | None = None
    EMAIL_FROM_EMAIL: str = Field(
        "info@example.com",
        validation_alias=AliasChoices("EMAIL_FROM_EMAIL", "EMAILS_FROM_EMAIL"),
    )
    EMAIL_FROM_NAME: str = Field(
        "FastAPI App",
        validation_alias=AliasChoices("EMAIL_FROM_NAME", "EMAILS_FROM_NAME"),
    )
    FRONTEND_URL: str = Field(
        "http://localhost",
        description="Frontend URL for email links (without port)",
    )

    # AI / OpenAI
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Langfuse observability
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # MCP server (FastMCP); must include /mcp path for HTTP transport
    MCP_SERVER_URL: str = "http://localhost:8001/mcp"

    # Long-term memory (per-user, cross-conversation). Independent of RAG
    # dimension; memories table owns its own VECTOR(MEMORY_EMBED_DIM) column.
    OLLAMA_HOST: str = "http://host.docker.internal:11434"
    MEMORY_EMBED_MODEL: str = "nomic-embed-text"
    MEMORY_EMBED_DIM: int = 768
    MEMORY_TOP_K: int = 5
    MEMORY_MIN_SIMILARITY: float = 0.7
    MEMORY_DEDUPE_SIMILARITY: float = 0.95
    MEMORY_EXTRACTION_MODEL: str | None = None  # falls back to OPENAI_MODEL when None
    MEMORY_HISTORY_LIMIT: int = 20
    MEMORY_EXTRACTION_TURNS: int = 6
    MEMORY_ENABLED: bool = True

    # Shared secret for service-to-service internal API calls (e.g. MCP -> backend)
    INTERNAL_API_TOKEN: str | None = None

    @property
    def REDIS_URL(self) -> str:
        """Return a full Redis URL (redis:// or rediss://)."""
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def DATABASE_URL(self) -> str:
        """Return async database URL for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Return sync database URL for Alembic migrations."""
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
