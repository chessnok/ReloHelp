"""Shared password strength rules for register and reset (ASCII-only, matches frontend)."""

from __future__ import annotations


def _has_ascii_upper(password: str) -> bool:
    return any(c.isascii() and c.isupper() for c in password)


def _has_ascii_lower(password: str) -> bool:
    return any(c.isascii() and c.islower() for c in password)


def _has_ascii_digit(password: str) -> bool:
    return any(c.isascii() and c.isdigit() for c in password)


def get_password_errors(password: str) -> list[str]:
    """Return human-readable validation errors (empty if password is valid)."""
    checks: tuple[tuple[bool, str], ...] = (
        (len(password) < 8, "Password must be at least 8 characters long"),
        (len(password) > 128, "Password must be at most 128 characters long"),
        (
            not _has_ascii_upper(password),
            "Password must contain at least one uppercase letter",
        ),
        (
            not _has_ascii_lower(password),
            "Password must contain at least one lowercase letter",
        ),
        (not _has_ascii_digit(password), "Password must contain at least one digit"),
    )
    return [message for failed, message in checks if failed]


def validate_password_strength(password: str) -> str:
    """Return the password if valid; raise ValueError listing all rule violations."""
    errors = get_password_errors(password)
    if errors:
        raise ValueError(", ".join(errors))
    return password
