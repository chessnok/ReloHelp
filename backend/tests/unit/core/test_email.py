"""Unit tests for app/core/email.py."""

from __future__ import annotations

import pytest

from app.core import email as email_mod
from app.core.config import settings


def test_render_template_password_reset_contains_link(monkeypatch):
    service = email_mod.EmailService()
    html = service.render_template(
        "email/password_reset.html",
        {"token": "T", "link": "http://x/reset?token=T", "subject": "Reset"},
    )
    assert "http://x/reset?token=T" in html


def test_render_template_verification_contains_link():
    service = email_mod.EmailService()
    html = service.render_template(
        "email/verification.html",
        {"token": "V", "link": "http://x/verify?token=V", "subject": "Verify"},
    )
    assert "http://x/verify?token=V" in html


async def test_send_password_reset_email_invokes_provider(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://front")
    service = email_mod.EmailService()
    captured: dict = {}

    class _Prov:
        async def send_email(self, to_email, subject, html_content, text_content=None):
            captured.update(
                to=to_email,
                subject=subject,
                html=html_content,
                text=text_content,
            )

    service.provider = _Prov()
    await service.send_password_reset_email("u@x.com", "TOK")
    assert captured["to"] == "u@x.com"
    assert "http://front/reset-password?token=TOK" in captured["html"]
    assert captured["text"] is not None


async def test_send_verification_email_invokes_provider(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://front")
    service = email_mod.EmailService()
    captured: dict = {}

    class _Prov:
        async def send_email(self, to_email, subject, html_content, text_content=None):
            captured.update(html=html_content)

    service.provider = _Prov()
    await service.send_verification_email("u@x.com", "VTOK")
    assert "http://front/verify-email?token=VTOK" in captured["html"]


async def test_resend_provider_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_API_KEY", None)
    prov = email_mod.ResendEmailProvider()
    with pytest.raises(ValueError):
        await prov.send_email("a@b.com", "s", "<p>x</p>")


async def test_resend_provider_posts_to_api(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_API_KEY", "k")
    captured = {}

    class _FakeResp:
        def raise_for_status(self):
            return None

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResp()

    monkeypatch.setattr(email_mod.httpx, "AsyncClient", lambda: _Client())
    prov = email_mod.ResendEmailProvider()
    await prov.send_email("u@x.com", "Hi", "<p>hi</p>", "hi")
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["json"]["to"] == ["u@x.com"]
    assert captured["headers"]["Authorization"] == "Bearer k"
