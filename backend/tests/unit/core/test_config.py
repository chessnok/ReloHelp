"""Unit tests for app/core/config.py."""

from __future__ import annotations

from app.core.config import Settings


def test_database_urls_built_from_components():
    s = Settings(DB_HOST="h", DB_PORT=1234, DB_USER="u", DB_PASSWORD="p", DB_NAME="n")
    assert s.DATABASE_URL == "postgresql+asyncpg://u:p@h:1234/n"
    assert s.DATABASE_URL_SYNC == "postgresql://u:p@h:1234/n"


def test_redis_url_without_password():
    s = Settings(REDIS_HOST="r", REDIS_PORT=1, REDIS_DB=2, REDIS_PASSWORD=None)
    assert s.REDIS_URL == "redis://r:1/2"


def test_redis_url_with_password():
    s = Settings(REDIS_HOST="r", REDIS_PORT=1, REDIS_DB=2, REDIS_PASSWORD="pw")
    assert s.REDIS_URL == "redis://:pw@r:1/2"


def test_email_alias_choices_accepts_legacy_names(monkeypatch):
    monkeypatch.setenv("EMAILS_FROM_EMAIL", "a@b.com")
    monkeypatch.setenv("EMAILS_FROM_NAME", "Legacy")
    s = Settings()
    assert s.EMAIL_FROM_EMAIL == "a@b.com"
    assert s.EMAIL_FROM_NAME == "Legacy"
