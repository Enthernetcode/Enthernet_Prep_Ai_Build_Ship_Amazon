from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WeaknessRecord(Base):
    __tablename__ = "weakness_records"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "competency_id", "dimension", name="uq_weakness_project_comp_dim"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("preparation_projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    competency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competency_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
