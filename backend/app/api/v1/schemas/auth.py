from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# Request schemas
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class PasswordForgotRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# Response schemas
class UserResponse(BaseModel):
    id: UUID
    email: str
    email_verified: bool
    is_active: str
    roles: list[str]
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def map_email_verified(cls, data: Any) -> Any:
        """Map email_is_verified to email_verified for API compatibility."""
        if isinstance(data, dict):
            if "email_is_verified" in data and "email_verified" not in data:
                data["email_verified"] = data.pop("email_is_verified")
        elif hasattr(data, "email_is_verified"):
            # For SQLAlchemy models
            data_dict = {
                "id": data.id,
                "email": data.email,
                "email_verified": data.email_is_verified,
                "is_active": data.is_active,
                "roles": data.roles if data.roles else [],
                "created_at": data.created_at,
            }
            return data_dict
        return data

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    user: UserResponse


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    ip: Optional[str]
    user_agent: Optional[str]

    class Config:
        from_attributes = True
