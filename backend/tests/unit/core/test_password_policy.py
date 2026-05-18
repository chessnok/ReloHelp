"""Unit tests for app/core/password_policy.py."""

from __future__ import annotations

import pytest

from app.core.password_policy import get_password_errors, validate_password_strength


class TestGetPasswordErrors:
    def test_valid_password(self):
        assert get_password_errors("Password1") == []

    def test_empty_password(self):
        errors = get_password_errors("")
        assert any("8 characters" in err for err in errors)
        assert len(errors) >= 4

    def test_password_over_128_chars(self):
        password = f"Password1{'x' * 122}"
        assert len(password) > 128
        errors = get_password_errors(password)
        assert any("128 characters" in err for err in errors)

    def test_unicode_password_rejected_like_frontend(self):
        # Cyrillic upper would pass Python isupper() but not ASCII /[A-Z]/
        errors = get_password_errors("Пароль1")
        assert any("uppercase" in err for err in errors)

    @pytest.mark.parametrize(
        "password,expected_substring",
        [
            ("short1A", "8 characters"),
            ("nouppercase1", "uppercase"),
            ("NOLOWER1", "lowercase"),
            ("NoDigitsHere", "digit"),
        ],
    )
    def test_invalid_passwords(self, password: str, expected_substring: str):
        errors = get_password_errors(password)
        assert len(errors) > 0
        assert any(expected_substring in err for err in errors)


class TestValidatePasswordStrength:
    def test_returns_password_when_valid(self):
        assert validate_password_strength("Password1") == "Password1"

    def test_raises_joined_errors_on_invalid(self):
        with pytest.raises(ValueError) as exc_info:
            validate_password_strength("x")
        message = str(exc_info.value)
        assert "8 characters" in message
        assert "uppercase" in message
        assert "lowercase" in message

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError) as exc_info:
            validate_password_strength("")
        assert "8 characters" in str(exc_info.value)

    def test_raises_on_password_over_128_chars(self):
        password = f"Password1{'x' * 122}"
        with pytest.raises(ValueError, match="128 characters"):
            validate_password_strength(password)
