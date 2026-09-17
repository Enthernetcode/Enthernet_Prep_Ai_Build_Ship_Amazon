"""session, competency, weakness, readiness tables

Revision ID: a1c2e4d6f001
Revises: 7e3c336989c5
Create Date: 2026-09-17 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1c2e4d6f001"
down_revision: Union[str, None] = "7e3c336989c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "competency_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("source_document_id", sa.UUID(), nullable=True),
        sa.Column("source_chunk_ordinal", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("mastery", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["preparation_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["documents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_competency_items_project_id"),
        "competency_items",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "preparation_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["preparation_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_preparation_sessions_project_id"),
        "preparation_sessions",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "session_turns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("competency_id", sa.UUID(), nullable=True),
        sa.Column("grounding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("user_answer", sa.Text(), nullable=True),
        sa.Column("evaluation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("adaptive_action", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("coach_note", sa.Text(), nullable=True),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["preparation_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"], ["competency_items.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "ordinal", name="uq_turn_session_ordinal"),
    )
    op.create_index(
        op.f("ix_session_turns_session_id"),
        "session_turns",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "weakness_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("competency_id", sa.UUID(), nullable=True),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["preparation_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"], ["competency_items.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "competency_id",
            "dimension",
            name="uq_weakness_project_comp_dim",
        ),
    )
    op.create_index(
        op.f("ix_weakness_records_project_id"),
        "weakness_records",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "readiness_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("overall", sa.Float(), nullable=False),
        sa.Column("knowledge", sa.Float(), nullable=False),
        sa.Column("communication", sa.Float(), nullable=False),
        sa.Column("evidence", sa.Float(), nullable=False),
        sa.Column("conciseness", sa.Float(), nullable=False),
        sa.Column("pressure", sa.Float(), nullable=False),
        sa.Column("consistency", sa.Float(), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["preparation_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["preparation_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_readiness_snapshots_project_id"),
        "readiness_snapshots",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_readiness_snapshots_project_id"), table_name="readiness_snapshots"
    )
    op.drop_table("readiness_snapshots")
    op.drop_index(
        op.f("ix_weakness_records_project_id"), table_name="weakness_records"
    )
    op.drop_table("weakness_records")
    op.drop_index(op.f("ix_session_turns_session_id"), table_name="session_turns")
    op.drop_table("session_turns")
    op.drop_index(
        op.f("ix_preparation_sessions_project_id"), table_name="preparation_sessions"
    )
    op.drop_table("preparation_sessions")
    op.drop_index(
        op.f("ix_competency_items_project_id"), table_name="competency_items"
    )
    op.drop_table("competency_items")
