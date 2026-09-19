"""MCP server exposing the preparation engine as agent tools.

Built for Alexa+ hackathon Alexa+ track (spec 2025-11-25, Streamable HTTP).

The MCP server mounts as a Starlette ASGI app at `/api/v1/mcp`. Every tool
authenticates via the Bearer token from the MCP request headers (same JWT the
web app uses) and calls the same session/agent code path as our REST API — no
duplicated business logic.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select

from app.agents.adaptive import AdaptivePlannerAgent
from app.agents.base import AgentContext
from app.agents.evaluator import EvaluatorAgent
from app.agents.examiner import ExaminerAgent
from app.agents.weakness import WeaknessAgent
from app.api.v1.readiness import _persist_snapshot
from app.api.v1.sessions import (
    _competency_candidates,
    _grounding_text,
    _recent_scores,
    _recompute_readiness,
    _upsert_weakness,
)
from app.auth import get_current_user
from app.db import AsyncSessionLocal
from app.models.competency import CompetencyItem
from app.models.project import PreparationProject
from app.models.readiness import ReadinessSnapshot
from app.models.session import PreparationSession, SessionTurn
from app.models.user import User
from app.readiness import baseline_from_coverage
from app.models.weakness import WeaknessRecord


mcp_server = MCPServer(
    name="enthernet-prep-ai",
    version="0.1.0",
    instructions=(
        "Enthernet Prep AI. Tools to run an adaptive, grounded interview "
        "preparation session: list projects, extract a competency map from "
        "the user's uploaded materials, start a session (mock_interview or "
        "final_boss), fetch the next question, submit an answer to get "
        "evaluation and an adaptive follow-up, and finish for a readiness "
        "report. Always call list_projects first if you don't have a "
        "project_id — never invent one."
    ),
)


def _bearer_token(ctx: Context) -> str:
    """Extract the JWT the MCP client attached to this request."""
    headers = getattr(ctx, "headers", None) or {}
    auth = headers.get("authorization") or headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise ToolError(
            "Authorization: Bearer <jwt> required. "
            "Log in via POST /api/v1/auth/login to obtain a token."
        )
    return auth.split(" ", 1)[1]


async def _resolve_user(ctx: Context, session) -> User:
    token = _bearer_token(ctx)
    return await get_current_user(token=token, session=session)


async def _load_owned_project(
    session, project_id: uuid.UUID, user: User
) -> PreparationProject:
    project = (
        await session.execute(
            select(PreparationProject).where(
                PreparationProject.id == project_id,
                PreparationProject.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise ToolError("project not found")
    return project


async def _load_owned_session(
    session, session_id: uuid.UUID, user: User
) -> tuple[PreparationSession, PreparationProject]:
    row = (
        await session.execute(
            select(PreparationSession, PreparationProject)
            .join(
                PreparationProject,
                PreparationProject.id == PreparationSession.project_id,
            )
            .where(
                PreparationSession.id == session_id,
                PreparationProject.user_id == user.id,
            )
        )
    ).first()
    if row is None:
        raise ToolError("session not found")
    return row[0], row[1]


# ─── Tools ───────────────────────────────────────────────────────────────────


@mcp_server.tool(
    name="prep.list_projects",
    title="List preparation projects",
    description=(
        "Return the authenticated user's preparation projects, newest first. "
        "Each project has an id, name, goal_type, target_date, and difficulty. "
        "Call this first when you don't already have a project_id."
    ),
)
async def list_projects(ctx: Context) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(ctx, session)
        rows = (
            await session.execute(
                select(PreparationProject)
                .where(PreparationProject.user_id == user.id)
                .order_by(PreparationProject.created_at.desc())
            )
        ).scalars().all()
        return {
            "projects": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "goal_type": p.goal_type,
                    "goal_description": p.goal_description,
                    "target_date": p.target_date.isoformat() if p.target_date else None,
                    "difficulty": p.difficulty,
                }
                for p in rows
            ]
        }


@mcp_server.tool(
    name="prep.extract_competencies",
    title="Extract competencies from uploaded documents",
    description=(
        "Run the Knowledge Extraction Agent over every processed chunk in the "
        "given project. Idempotent — safe to call again after new uploads. "
        "Returns the total competency count and a per-kind breakdown."
    ),
)
async def extract_competencies(ctx: Context, project_id: str) -> dict[str, Any]:
    from app.agents.knowledge import KnowledgeExtractionAgent
    from app.models.chunk import DocumentChunk
    from app.models.document import Document

    async with AsyncSessionLocal() as session:
        user = await _resolve_user(ctx, session)
        project = await _load_owned_project(session, uuid.UUID(project_id), user)

        rows = (
            await session.execute(
                select(
                    DocumentChunk.document_id,
                    DocumentChunk.ordinal,
                    DocumentChunk.text,
                )
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(Document.project_id == project.id)
                .order_by(Document.created_at.asc(), DocumentChunk.ordinal.asc())
            )
        ).all()
        if not rows:
            raise ToolError(
                "No processed chunks in this project. Upload documents first."
            )
        agent = KnowledgeExtractionAgent()
        result = await agent.execute(
            AgentContext(user_id=str(user.id), project_id=str(project.id)),
            tools={
                "chunks": [
                    {"document_id": str(r.document_id), "ordinal": r.ordinal, "text": r.text}
                    for r in rows
                ]
            },
        )
        existing = (
            await session.execute(
                select(CompetencyItem).where(CompetencyItem.project_id == project.id)
            )
        ).scalars().all()
        existing_map = {(c.kind, c.label.lower()): c for c in existing}
        kept = 0
        for item in result.result["items"]:
            key = (item["kind"], item["label"].lower())
            if key in existing_map:
                continue
            session.add(
                CompetencyItem(
                    project_id=project.id,
                    kind=item["kind"],
                    label=item["label"][:300],
                    confidence=item["confidence"],
                    source_document_id=(
                        uuid.UUID(item["source_document_id"])
                        if item.get("source_document_id")
                        else None
                    ),
                    source_chunk_ordinal=item.get("source_chunk_ordinal"),
                )
            )
            kept += 1
        await session.commit()
        total = (
            await session.execute(
                select(CompetencyItem).where(CompetencyItem.project_id == project.id)
            )
        ).scalars().all()
        # Also refresh baseline readiness so the next tool call sees an up-to-date snapshot.
        kinds: dict[str, int] = {}
        for c in total:
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
        baseline = baseline_from_coverage(len(total), kinds)
        snapshot = ReadinessSnapshot(
            project_id=project.id,
            session_id=None,
            source="baseline",
            overall=baseline["overall"],
            knowledge=baseline["knowledge"],
            communication=baseline["communication"],
            evidence=baseline["evidence"],
            conciseness=baseline["conciseness"],
            pressure=baseline["pressure"],
            consistency=baseline["consistency"],
            coverage=baseline["coverage"],
            detail=baseline.get("detail"),
        )
        session.add(snapshot)
        await session.commit()
        return {
            "project_id": str(project.id),
            "kept": kept,
            "total": len(total),
            "kinds": kinds,
            "baseline_readiness": baseline["overall"],
        }


@mcp_server.tool(
    name="prep.get_readiness",
    title="Get the latest readiness snapshot",
    description=(
        "Return the latest deterministic readiness snapshot for the project. "
        "Includes an overall score in [0,1] plus per-dimension scores: "
        "knowledge, communication, evidence, conciseness, pressure, "
        "consistency, coverage."
    ),
)
async def get_readiness(ctx: Context, project_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(ctx, session)
        await _load_owned_project(session, uuid.UUID(project_id), user)
        snap = (
            await session.execute(
                select(ReadinessSnapshot)
                .where(ReadinessSnapshot.project_id == uuid.UUID(project_id))
                .order_by(ReadinessSnapshot.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snap is None:
            raise ToolError(
                "No readiness snapshot yet. Call prep.extract_competencies "
                "first (or upload documents)."
            )
        return {
            "source": snap.source,
            "overall": snap.overall,
            "knowledge": snap.knowledge,
            "communication": snap.communication,
            "evidence": snap.evidence,
            "conciseness": snap.conciseness,
            "pressure": snap.pressure,
            "consistency": snap.consistency,
            "coverage": snap.coverage,
            "created_at": snap.created_at.isoformat(),
        }


@mcp_server.tool(
    name="prep.start_session",
    title="Start a preparation session",
    description=(
        "Begin an interview session for the given project. `mode` is one of "
        "'mock_interview' (hints on, adaptive difficulty) or 'final_boss' "
        "(no hints, longer, produces the final graded report). Returns the "
        "session_id to use in subsequent tool calls."
    ),
)
async def start_session(
    ctx: Context,
    project_id: str,
    mode: str = "mock_interview",
    difficulty: int = 3,
) -> dict[str, Any]:
    if mode not in {"mock_interview", "final_boss", "weakness_drill", "study", "quiz"}:
        raise ToolError(f"invalid mode: {mode}")
    difficulty = max(1, min(6, int(difficulty)))
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(ctx, session)
        project = await _load_owned_project(session, uuid.UUID(project_id), user)
        has_comp = (
            await session.execute(
                select(CompetencyItem.id)
                .where(CompetencyItem.project_id == project.id)
                .limit(1)
            )
        ).first()
        if has_comp is None:
            raise ToolError(
                "Project has no competency map. Call "
                "prep.extract_competencies first."
            )
        prep = PreparationSession(
            project_id=project.id, mode=mode, difficulty=difficulty
        )
        session.add(prep)
        await session.commit()
        await session.refresh(prep)
        return {
            "session_id": str(prep.id),
            "project_id": str(project.id),
            "mode": prep.mode,
            "difficulty": prep.difficulty,
            "status": prep.status,
        }


@mcp_server.tool(
    name="prep.next_question",
    title="Ask the examiner for the next question",
    description=(
        "Generate the next grounded question for the session. If there is "
        "already an unanswered question, return that instead — this tool is "
        "idempotent within a turn."
    ),
)
async def next_question(ctx: Context, session_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(ctx, session)
        prep, project = await _load_owned_session(session, uuid.UUID(session_id), user)
        if prep.status != "active":
            raise ToolError("session is not active")

        open_turn = (
            await session.execute(
                select(SessionTurn)
                .where(
                    SessionTurn.session_id == prep.id,
                    SessionTurn.user_answer.is_(None),
                )
                .order_by(SessionTurn.ordinal.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if open_turn is not None:
            return _turn_payload(open_turn)

        ordinal_row = (
            await session.execute(
                select(SessionTurn.ordinal)
                .where(SessionTurn.session_id == prep.id)
                .order_by(SessionTurn.ordinal.desc())
                .limit(1)
            )
        ).first()
        next_ordinal = (ordinal_row[0] + 1) if ordinal_row else 1

        candidates = await _competency_candidates(session, project.id)
        asked_rows = (
            await session.execute(
                select(SessionTurn.topic).where(SessionTurn.session_id == prep.id)
            )
        ).all()
        asked_labels = [r[0] for r in asked_rows if r[0]]

        agent_result = await ExaminerAgent().execute(
            AgentContext(
                user_id=str(user.id),
                project_id=str(project.id),
                session_id=str(prep.id),
                goal_type=project.goal_type,
                difficulty=prep.difficulty,
            ),
            tools={
                "candidates": candidates,
                "asked_labels": asked_labels,
                "difficulty": prep.difficulty,
                "seed": next_ordinal,
            },
        )
        if agent_result.status != "success":
            raise ToolError(
                agent_result.result.get("reason", "examiner failed")
            )
        comp_id_raw = agent_result.result.get("competency_id")
        turn = SessionTurn(
            session_id=prep.id,
            ordinal=next_ordinal,
            question=agent_result.result["question"],
            topic=agent_result.result["topic"],
            difficulty=agent_result.result["difficulty"],
            competency_id=uuid.UUID(comp_id_raw) if comp_id_raw else None,
            grounding=agent_result.result["grounding"],
        )
        session.add(turn)
        await session.commit()
        await session.refresh(turn)
        return _turn_payload(turn)


@mcp_server.tool(
    name="prep.submit_answer",
    title="Submit an answer for evaluation",
    description=(
        "Evaluate the user's answer to the current turn. Runs the full loop: "
        "multi-dimensional rubric scoring, weakness map update, adaptive "
        "planner decision, and readiness recompute. Returns the evaluation, "
        "the planner's next action, and — if the planner chose to finish — "
        "the final summary."
    ),
)
async def submit_answer(
    ctx: Context,
    session_id: str,
    ordinal: int,
    answer: str,
    seconds_taken: float | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(ctx, session)
        prep, project = await _load_owned_session(session, uuid.UUID(session_id), user)
        if prep.status != "active":
            raise ToolError("session is not active")
        turn = (
            await session.execute(
                select(SessionTurn).where(
                    SessionTurn.session_id == prep.id,
                    SessionTurn.ordinal == int(ordinal),
                )
            )
        ).scalar_one_or_none()
        if turn is None:
            raise ToolError("turn not found")
        if turn.user_answer is not None:
            raise ToolError("turn already answered")

        grounding_text = await _grounding_text(session, turn.grounding)
        ev = await EvaluatorAgent().execute(
            AgentContext(
                user_id=str(user.id),
                project_id=str(project.id),
                session_id=str(prep.id),
                goal_type=project.goal_type,
                difficulty=turn.difficulty,
            ),
            tools={
                "answer": answer,
                "topic": turn.topic or "",
                "grounding_text": grounding_text,
                "difficulty": turn.difficulty,
                "seconds_taken": seconds_taken,
                "mode": prep.mode,
            },
        )
        if turn.competency_id is not None:
            competency = await session.get(CompetencyItem, turn.competency_id)
            if competency is not None:
                competency.attempts += 1
                if ev.result["overall"] >= 0.7:
                    competency.correct += 1
                weight = 1 / competency.attempts
                competency.mastery = round(
                    (1 - weight) * competency.mastery + weight * ev.result["overall"],
                    4,
                )
        current_severity: dict[str, float] = {}
        if turn.competency_id is not None:
            rows = (
                await session.execute(
                    select(WeaknessRecord).where(
                        WeaknessRecord.project_id == project.id,
                        WeaknessRecord.competency_id == turn.competency_id,
                    )
                )
            ).scalars().all()
            current_severity = {r.dimension: r.severity for r in rows}
        weakness_result = await WeaknessAgent().execute(
            AgentContext(
                user_id=str(user.id),
                project_id=str(project.id),
                session_id=str(prep.id),
            ),
            tools={
                "dimensions": ev.result["dimensions"],
                "current_severity": current_severity,
            },
        )
        await _upsert_weakness(
            session, project.id, turn.competency_id, weakness_result.result["updates"]
        )
        recent_dims = await _recent_scores(session, prep.id, limit=6)
        recent_overalls = [
            row.get("accuracy", 0.6) * 0.5 + row.get("completeness", 0.6) * 0.5
            for row in recent_dims
        ]
        max_severity = max(
            (u["severity"] for u in weakness_result.result["updates"]), default=0.0
        )
        turns_so_far = (
            await session.execute(
                select(SessionTurn.id).where(SessionTurn.session_id == prep.id)
            )
        ).all()
        plan = await AdaptivePlannerAgent().execute(
            AgentContext(
                user_id=str(user.id),
                project_id=str(project.id),
                session_id=str(prep.id),
                goal_type=project.goal_type,
                difficulty=turn.difficulty,
            ),
            tools={
                "overall": ev.result["overall"],
                "difficulty": turn.difficulty,
                "recent_scores": recent_overalls,
                "weakness_severity": max_severity,
                "mode": prep.mode,
                "topic": turn.topic or "",
                "turns_taken": len(turns_so_far),
                "max_turns": 10 if prep.mode == "final_boss" else 8,
            },
        )
        now = datetime.now(timezone.utc)
        turn.user_answer = answer
        turn.evaluation = ev.result
        turn.adaptive_action = plan.result
        turn.coach_note = plan.result.get("coach_note")
        turn.answered_at = now
        prep.difficulty = plan.result["next_difficulty"]
        await session.commit()
        snapshot = await _recompute_readiness(
            session, project.id, prep.id, source="turn"
        )
        return {
            "evaluation": ev.result,
            "adaptive_action": plan.result,
            "readiness": {
                "overall": snapshot.overall,
                "knowledge": snapshot.knowledge,
                "communication": snapshot.communication,
                "evidence": snapshot.evidence,
                "conciseness": snapshot.conciseness,
                "pressure": snapshot.pressure,
                "consistency": snapshot.consistency,
                "coverage": snapshot.coverage,
            },
            "should_finish": plan.result["should_finish"],
        }


@mcp_server.tool(
    name="prep.finish_session",
    title="Finish the session and get the final readiness report",
    description=(
        "Mark the session complete and compute the final readiness snapshot. "
        "Idempotent — safe to call after the planner already flagged finish."
    ),
)
async def finish_session(ctx: Context, session_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(ctx, session)
        prep, project = await _load_owned_session(session, uuid.UUID(session_id), user)
        if prep.status == "completed":
            snap = (
                await session.execute(
                    select(ReadinessSnapshot)
                    .where(ReadinessSnapshot.session_id == prep.id)
                    .order_by(ReadinessSnapshot.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _finish_payload(prep, snap)
        source = "final_boss" if prep.mode == "final_boss" else "session"
        snapshot = await _recompute_readiness(session, project.id, prep.id, source=source)
        turns = (
            await session.execute(
                select(SessionTurn)
                .where(SessionTurn.session_id == prep.id)
                .order_by(SessionTurn.ordinal.asc())
            )
        ).scalars().all()
        answered = [t for t in turns if t.user_answer is not None]
        avg = (
            sum(t.evaluation.get("overall", 0.0) for t in answered) / len(answered)
            if answered
            else 0.0
        )
        prep.status = "completed"
        prep.completed_at = datetime.now(timezone.utc)
        prep.summary = {
            "turns_answered": len(answered),
            "turns_total": len(turns),
            "average_turn_score": round(avg, 4),
            "final_readiness": snapshot.overall,
            "mode": prep.mode,
        }
        await session.commit()
        await session.refresh(prep)
        return _finish_payload(prep, snapshot)


def _turn_payload(turn: SessionTurn) -> dict[str, Any]:
    return {
        "turn_id": str(turn.id),
        "session_id": str(turn.session_id),
        "ordinal": turn.ordinal,
        "question": turn.question,
        "topic": turn.topic,
        "difficulty": turn.difficulty,
        "grounding": turn.grounding,
    }


def _finish_payload(
    prep: PreparationSession, snap: ReadinessSnapshot | None
) -> dict[str, Any]:
    payload = {
        "session_id": str(prep.id),
        "status": prep.status,
        "summary": prep.summary,
    }
    if snap is not None:
        payload["readiness"] = {
            "overall": snap.overall,
            "knowledge": snap.knowledge,
            "communication": snap.communication,
            "evidence": snap.evidence,
            "conciseness": snap.conciseness,
            "pressure": snap.pressure,
            "consistency": snap.consistency,
            "coverage": snap.coverage,
        }
    return payload


def build_mcp_asgi_app():
    """Return the Starlette ASGI app that speaks Streamable HTTP at '/'.

    Callers mount this under `/api/v1/mcp` in the FastAPI app so the full
    endpoint URL is `POST /api/v1/mcp`.
    """
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=["*"],
        allowed_origins=["*"],
    )
    return mcp_server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        transport_security=security,
    )
