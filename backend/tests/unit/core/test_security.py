"""Unit tests for app/core/security.py."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core import security


class TestPasswordHashing:
    def test_hash_then_verify_succeeds(self):
        h = security.hash_password("Password123")
        assert h != "Password123"
        assert security.verify_password("Password123", h) is True

    def test_verify_wrong_password_returns_false(self):
        h = security.hash_password("Password123")
        assert security.verify_password("WrongPass1", h) is False

    def test_hash_is_non_deterministic(self):
        assert security.hash_password("x") != security.hash_password("x")


class TestCSRF:
    def test_generate_then_verify(self):
        t = security.generate_csrf_token()
        assert security.verify_csrf_token(t) is True

    def test_verify_invalid_token_returns_false(self):
        assert security.verify_csrf_token("not-a-real-token") is False


class TestAccessToken:
    def test_decode_returns_payload(self):
        uid = uuid4()
        jti = uuid4()
        token = security.create_access_token(uid, "u@x.com", ["admin"], jti)
        payload = security.decode_token(token)
        assert payload["sub"] == str(uid)
        assert payload["jti"] == str(jti)
        assert payload["email"] == "u@x.com"
        assert payload["roles"] == ["admin"]
        assert payload["type"] == "access"

    def test_decode_expired_raises_401(self):
        token = security.create_access_token(
            uuid4(),
            "u@x.com",
            [],
            uuid4(),
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(HTTPException) as exc:
            security.decode_token(token)
        assert exc.value.status_code == 401

    def test_decode_tampered_raises_401(self):
        token = security.create_access_token(uuid4(), "u@x.com", [], uuid4())
        with pytest.raises(HTTPException) as exc:
            security.decode_token(token + "x")
        assert exc.value.status_code == 401


class TestRefreshToken:
    def test_create_and_decode_roundtrip(self):
        jti = uuid4()
        rnd = security.generate_refresh_token_value()
        token = security.create_refresh_token(jti, rnd)
        payload, returned_rnd = security.decode_refresh_token(token)
        assert payload["jti"] == str(jti)
        assert payload["type"] == "refresh"
        assert returned_rnd == rnd

    def test_decode_malformed_jwt_part_raises_401(self):
        # Length check passes (has a dot) but jwt body is invalid.
        with pytest.raises(HTTPException) as exc:
            security.decode_refresh_token("not.ajwt")
        assert exc.value.status_code == 401

    def test_decode_no_dot_raises_value_error(self):
        # decode_refresh_token's format guard raises ValueError when no '.'.
        with pytest.raises(ValueError):
            security.decode_refresh_token("notajwt")

    def test_decode_expired_raises_401(self):
        token = security.create_refresh_token(
            uuid4(),
            security.generate_refresh_token_value(),
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(HTTPException) as exc:
            security.decode_refresh_token(token)
        assert exc.value.status_code == 401

    def test_hash_and_verify_refresh_token(self):
        rnd = security.generate_refresh_token_value()
        h = security.hash_refresh_token(rnd)
        assert security.verify_refresh_token(rnd, h) is True
        assert security.verify_refresh_token(rnd + "x", h) is False


class TestTokenGenerators:
    def test_email_verification_token_unique(self):
        a = security.generate_email_verification_token()
        b = security.generate_email_verification_token()
        assert a != b and len(a) > 20

    def test_password_reset_token_unique(self):
        a = security.generate_password_reset_token()
        b = security.generate_password_reset_token()
        assert a != b and len(a) > 20

    def test_refresh_token_value_unique(self):
        a = security.generate_refresh_token_value()
        b = security.generate_refresh_token_value()
        assert a != b and len(a) > 50
