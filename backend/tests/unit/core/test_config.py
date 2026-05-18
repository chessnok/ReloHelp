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


def test_allowed_origins_default_is_wildcard():
    s = Settings()
    assert s.ALLOWED_ORIGINS == ["*"]


def test_allowed_origins_single_wildcard_from_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    s = Settings()
    assert s.ALLOWED_ORIGINS == ["*"]


def test_allowed_origins_comma_separated_list(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://a.example.com, https://b.example.com ,https://c.example.com",
    )
    s = Settings()
    assert s.ALLOWED_ORIGINS == [
        "https://a.example.com",
        "https://b.example.com",
        "https://c.example.com",
    ]


def test_allowed_origins_json_array(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS", '["https://a.example.com", "https://b.example.com"]'
    )
    s = Settings()
    assert s.ALLOWED_ORIGINS == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_allowed_origins_empty_string_falls_back_to_wildcard(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    s = Settings()
    assert s.ALLOWED_ORIGINS == ["*"]


def test_allowed_origins_single_origin(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://only.example.com")
    s = Settings()
    assert s.ALLOWED_ORIGINS == ["https://only.example.com"]


def test_allowed_origins_validator_passthrough_for_list():
    s = Settings(ALLOWED_ORIGINS=["https://x.example.com"])
    assert s.ALLOWED_ORIGINS == ["https://x.example.com"]


def test_allowed_origins_validator_handles_none():
    assert Settings._parse_allowed_origins(None) == ["*"]
