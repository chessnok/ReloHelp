"""Per-user long-term memory backed by pgvector."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.db import Base

# Vector dimension is fixed at table-creation time and cannot be changed
# without a migration. Runtime MEMORY_EMBED_DIM must match the value used
# in the alembic migration that created this column.
_EMBED_DIM = settings.MEMORY_EMBED_DIM


class Memory(Base):
    __tablename__ = "memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind = Column(Text, nullable=False)  # fact | preference | event | summary
    content = Column(Text, nullable=False)
    embedding = Column(Vector(_EMBED_DIM), nullable=False)
    meta = Column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User", backref="memories", lazy="selectin")

    __table_args__ = (Index("ix_memories_user_id", "user_id"),)
