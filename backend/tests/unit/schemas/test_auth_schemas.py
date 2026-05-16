"""Unit tests for app/api/v1/schemas/auth.py."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordForgotRequest,
    PasswordResetRequest,
    RegisterRequest,
    SessionResponse,
    UserResponse,
    VerifyEmailRequest,
)


class TestRegisterRequest:
    def test_valid(self):
        r = RegisterRequest(email="u@x.com", password="Password1")
        assert r.email == "u@x.com"

    @pytest.mark.parametrize(
        "pw",
        ["short1A", "nouppercase1", "NOLOWER1", "NoDigitsHere"],
    )
    def test_invalid_passwords(self, pw):
        with pytest.raises(ValidationError):
            RegisterRequest(email="u@x.com", password=pw)

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="Password1")


class TestPasswordResetRequest:
    def test_valid(self):
        r = PasswordResetRequest(token="t", new_password="Password1")
        assert r.token == "t"

    def test_weak_password_rejected(self):
        with pytest.raises(ValidationError):
            PasswordResetRequest(token="t", new_password="weakpass")


class TestSimpleSchemas:
    def test_login_request(self):
        r = LoginRequest(email="a@b.com", password="anything")
        assert r.password == "anything"

    def test_verify_email_request(self):
        assert VerifyEmailRequest(token="v").token == "v"

    def test_password_forgot_request(self):
        assert PasswordForgotRequest(email="a@b.com").email == "a@b.com"


class TestUserResponse:
    def test_maps_email_is_verified_attr(self):
        class _U:
            id = uuid4()
            email = "u@x.com"
            email_is_verified = True
            is_active = "active"
            roles = ["admin"]
            created_at = datetime.now(timezone.utc)

        r = UserResponse.model_validate(_U())
        assert r.email_verified is True
        assert r.roles == ["admin"]

    def test_maps_email_is_verified_dict(self):
        r = UserResponse.model_validate(
            {
                "id": uuid4(),
                "email": "u@x.com",
                "email_is_verified": False,
                "is_active": "active",
                "roles": [],
                "created_at": datetime.now(timezone.utc),
            }
        )
        assert r.email_verified is False

    def test_login_response_nests_user(self):
        u = UserResponse(
            id=uuid4(),
            email="u@x.com",
            email_verified=True,
            is_active="active",
            roles=[],
            created_at=datetime.now(timezone.utc),
        )
        resp = LoginResponse(user=u)
        assert resp.user.email == "u@x.com"


def test_session_response_from_attributes():
    class _S:
        id = uuid4()
        created_at = datetime.now(timezone.utc)
        last_used_at = datetime.now(timezone.utc)
        expires_at = datetime.now(timezone.utc)
        ip = "1.2.3.4"
        user_agent = "ua"

    r = SessionResponse.model_validate(_S())
    assert r.ip == "1.2.3.4"
