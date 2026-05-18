"""Shared password strength rules for register and reset."""

from __future__ import annotations


def get_password_errors(password: str) -> list[str]:
    """Return human-readable validation errors (empty if password is valid)."""
    errors: list[str] = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    if len(password) > 128:
        errors.append("Password must be at most 128 characters long")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")
    return errors


def validate_password_strength(password: str) -> str:
    """Return the password if valid; raise ValueError with the first rule violation."""
    errors = get_password_errors(password)
    if errors:
        raise ValueError(errors[0])
    return password
