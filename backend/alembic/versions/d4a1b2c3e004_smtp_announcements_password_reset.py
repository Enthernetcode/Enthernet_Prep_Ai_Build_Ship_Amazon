"""smtp_configs + announcements + password_reset_tokens

Revision ID: d4a1b2c3e004
Revises: c3e7f9a1b003
Create Date: 2026-09-19 14:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4a1b2c3e004"
down_revision: Union[str, None] = "c3e7f9a1b003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "smtp_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("password", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("from_address", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("from_name", sa.String(length=255), nullable=False, server_default="Enthernet Prep AI"),
        sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("use_starttls", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO smtp_configs (id) VALUES (gen_random_uuid())
        """
    )

    op.create_table(
        "announcements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("audience", sa.String(length=16), nullable=False, server_default="all"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_token_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("announcements")
    op.drop_table("smtp_configs")
