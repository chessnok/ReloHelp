import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status
from itsdangerous import URLSafeTimedSerializer

from app.core.config import settings

# Password hasher
password_hasher = PasswordHasher()

# CSRF token serializer
csrf_serializer = URLSafeTimedSerializer(settings.CSRF_SECRET_KEY)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        password_hasher.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return csrf_serializer.dumps(secrets.token_urlsafe(32))


def verify_csrf_token(token: str, max_age: int = 3600) -> bool:
    """Verify a CSRF token."""
    try:
        csrf_serializer.loads(token, max_age=max_age)
        return True
    except Exception:
        return False


def create_access_token(
    user_id: UUID,
    email: str,
    roles: list[str],
    jti: UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": str(user_id),
        "email": email,
        "roles": roles,
        "jti": str(jti),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(
    jti: UUID, random_part: str, expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT refresh token with embedded random part.

    Format: JWT.random_part where JWT contains JTI for lookup.
    The random_part is hashed and stored in DB for replay detection.
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "jti": str(jti),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    jwt_part = jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return f"{jwt_part}.{random_part}"


def decode_refresh_token(token: str) -> tuple[dict, str]:
    """Decode refresh token and return (payload, random_part)."""
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError("Invalid token format")

        jwt_part, random_part = parts
        payload = jwt.decode(
            jwt_part, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload, random_part
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


def generate_refresh_token_value() -> str:
    """Generate a random refresh token value (64+ bytes)."""
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage."""
    return hash_password(token)  # Reuse password hasher for refresh tokens


def verify_refresh_token(plain_token: str, hashed_token: str) -> bool:
    """Verify a refresh token against its hash."""
    return verify_password(plain_token, hashed_token)


def generate_email_verification_token() -> str:
    """Generate a secure token for email verification."""
    return secrets.token_urlsafe(32)


def generate_password_reset_token() -> str:
    """Generate a secure token for password reset."""
    return secrets.token_urlsafe(32)
