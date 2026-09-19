"""add missing embedding column to document_chunks

The initial `7e3c336989c5` migration declared the chunks table but never added
the `embedding` pgvector column that `app.models.chunk.DocumentChunk` requires.
This repair migration brings the schema in line with the model so ingest and
retrieval work end-to-end.

Revision ID: b2d5f7e8a002
Revises: a1c2e4d6f001
Create Date: 2026-09-17 13:45:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from app.config import settings


revision: str = "b2d5f7e8a002"
down_revision: Union[str, None] = "a1c2e4d6f001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(settings.embedding_dimensions), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "embedding")
