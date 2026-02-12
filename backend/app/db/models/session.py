from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql.base import UUID
from sqlalchemy.orm import relationship

from app.db import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, index=True)  # JTI
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash = Column(String, nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    rotation_counter = Column(Integer, default=0, nullable=False)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    # Relationships
    user = relationship("User", back_populates="sessions", lazy="selectin")
