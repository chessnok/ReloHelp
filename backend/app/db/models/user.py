from sqlalchemy import ARRAY, Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.postgresql.base import UUID
from sqlalchemy.orm import relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    email = Column(String, unique=True, index=True)
    email_is_verified = Column(Boolean, default=False)
    hashed_password = Column(String)
    is_active = Column(String, default="active")
    roles = Column(ARRAY(String), default=[], nullable=False)

    # Relationships
    sessions = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    email_verification_tokens = relationship(
        "EmailVerificationToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    password_reset_tokens = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
