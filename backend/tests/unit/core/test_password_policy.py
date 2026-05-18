"""Unit tests for app/core/password_policy.py."""

from __future__ import annotations

import pytest

from app.core.password_policy import get_password_errors, validate_password_strength


class TestGetPasswordErrors:
    def test_valid_password(self):
        assert get_password_errors("Password1") == []

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

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError, match="uppercase"):
            validate_password_strength("password1")
