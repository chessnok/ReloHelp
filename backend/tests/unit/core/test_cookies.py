"""Unit tests for app/core/cookies.py."""

from __future__ import annotations

from fastapi import Response

from app.core import cookies


def _cookie_headers(response: Response) -> list[str]:
    return response.headers.getlist("set-cookie")


def _named(response: Response) -> dict[str, str]:
    return {raw.split("=", 1)[0]: raw for raw in _cookie_headers(response)}


def test_set_access_token_cookie_attrs():
    r = Response()
    cookies.set_access_token_cookie(r, "tok")
    header = _named(r)["access_token"]
    assert "access_token=tok" in header
    assert "HttpOnly" in header
    assert "Path=/" in header


def test_set_refresh_token_cookie_path_scoped():
    r = Response()
    cookies.set_refresh_token_cookie(r, "rtok")
    header = _named(r)["refresh_token"]
    assert "refresh_token=rtok" in header
    assert "HttpOnly" in header
    assert "Path=/auth/token/refresh" in header


def test_set_csrf_token_cookie_not_httponly():
    r = Response()
    cookies.set_csrf_token_cookie(r, "csrf")
    header = _named(r)["csrf_token"]
    assert "csrf_token=csrf" in header
    assert "HttpOnly" not in header


def test_delete_auth_cookies_emits_three_headers():
    r = Response()
    cookies.delete_auth_cookies(r)
    names = {h.split("=", 1)[0] for h in _cookie_headers(r)}
    assert {"access_token", "refresh_token", "csrf_token"} <= names
