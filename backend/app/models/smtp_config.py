from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SmtpConfig(Base):
    """Single-row table (id fixed) holding the platform's outbound email
    configuration. Password is stored in plain text at rest; the admin UI
    tries hard to hide it in transit but this is a demo-scoped deployment.

    Fields kept nullable for clean "unconfigured" state — mail sending refuses
    to run until `enabled=True` and `host` is populated."""

    __tablename__ = "smtp_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    username: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    password: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    from_address: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    from_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Enthernet Prep AI")
    use_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    use_starttls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
