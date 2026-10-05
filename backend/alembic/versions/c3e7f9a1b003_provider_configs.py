"""provider_configs table

Revision ID: c3e7f9a1b003
Revises: b2d5f7e8a002
Create Date: 2026-09-19 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3e7f9a1b003"
down_revision: Union[str, None] = "b2d5f7e8a002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("llm_provider", sa.String(length=32), nullable=False),
        sa.Column("llm_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_provider", sa.String(length=32), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", name="uq_provider_config_scope"),
    )

    # Seed rows: one per scope. Defaults are the safe (mock) provider so a
    # freshly-migrated instance never accidentally spends API dollars.
    op.execute(
        """
        INSERT INTO provider_configs
            (id, scope, llm_provider, llm_model, embedding_provider, embedding_model)
        VALUES
            (gen_random_uuid(), 'judged', 'mock', 'gpt-4o-mini',
             'mock', 'text-embedding-3-small'),
            (gen_random_uuid(), 'lab',    'mock', 'gpt-4o-mini',
             'mock', 'text-embedding-3-small')
        """
    )


def downgrade() -> None:
    op.drop_table("provider_configs")
