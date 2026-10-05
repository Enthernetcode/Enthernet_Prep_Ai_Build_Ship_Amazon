from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProviderConfig(Base):
    """Per-scope LLM + embedding provider configuration.

    Two rows exist: `judged` (mirrors settings, updated only by env changes)
    and `lab` (admin-editable via /api/v1/admin/providers).
    """

    __tablename__ = "provider_configs"
    __table_args__ = (
        UniqueConstraint("scope", name="uq_provider_config_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
