from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import readiness as readiness_engine
from app.agents.adaptive import AdaptivePlannerAgent
from app.agents.base import AgentContext
from app.agents.coach import CoachAgent
from app.agents.evaluator import EvaluatorAgent
from app.agents.examiner import ExaminerAgent
from app.agents.weakness import WeaknessAgent
from app.api.v1.readiness import _persist_snapshot
from app.auth import get_current_user
from app.db import get_session
from app.models.chunk import DocumentChunk
from app.models.competency import CompetencyItem
from app.models.project import PreparationProject
from app.models.readiness import ReadinessSnapshot
from app.models.session import PreparationSession, SessionTurn
from app.models.user import User
from app.models.weakness import WeaknessRecord
from app.schemas.session import (
    SessionCreate,
    SessionResponse,
    SessionWithTurns,
    TurnAnswer,
    TurnResponse,
)

# The `sessions` router is mounted at /sessions; the create-session
# endpoint is nested under a project and exposed via `project_router`.
router = APIRouter()
project_router = APIRouter()


async def _load_owned_project(
    project_id: uuid.UUID, user: User, session: AsyncSession
) -> PreparationProject:
    result = await session.execute(
        select(PreparationProject).where(
            PreparationProject.id == project_id,
            PreparationProject.user_id == user.id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _load_owned_session(
    session_id: uuid.UUID, user: User, session: AsyncSession
) -> tuple[PreparationSession, PreparationProject]:
    stmt = (
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
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return row[0], row[1]


async def _competency_candidates(
    session: AsyncSession, project_id: uuid.UUID
) -> list[dict[str, Any]]:
    competencies = (
        await session.execute(
            select(CompetencyItem).where(CompetencyItem.project_id == project_id)
        )
    ).scalars().all()
    if not competencies:
        return []
    weakness_rows = (
        await session.execute(
            select(WeaknessRecord).where(WeaknessRecord.project_id == project_id)
        )
    ).scalars().all()
    weakness_by_comp: dict[uuid.UUID, float] = {}
    for w in weakness_rows:
        if w.competency_id is not None:
            weakness_by_comp[w.competency_id] = max(
                weakness_by_comp.get(w.competency_id, 0.0), w.severity
            )
    return [
        {
            "id": str(c.id),
            "kind": c.kind,
            "label": c.label,
            "source_document_id": str(c.source_document_id) if c.source_document_id else None,
            "source_chunk_ordinal": c.source_chunk_ordinal,
            "confidence": c.confidence,
            "mastery": c.mastery,
            "attempts": c.attempts,
            "weakness_severity": weakness_by_comp.get(c.id, 0.0),
        }
        for c in competencies
    ]


async def _grounding_text(
    session: AsyncSession, grounding: dict[str, Any] | None
) -> str:
    if not grounding:
        return ""
    doc_id = grounding.get("source_document_id")
    ordinal = grounding.get("source_chunk_ordinal")
    if not doc_id or ordinal is None:
        return grounding.get("competency_label", "") or ""
    chunk = (
        await session.execute(
            select(DocumentChunk.text)
            .where(
                DocumentChunk.document_id == uuid.UUID(doc_id),
                DocumentChunk.ordinal == ordinal,
            )
        )
    ).scalar_one_or_none()
    return chunk or grounding.get("competency_label", "") or ""


async def _recent_scores(
    session: AsyncSession, session_id: uuid.UUID, limit: int = 6
) -> list[dict[str, float]]:
    rows = (
        await session.execute(
            select(SessionTurn.evaluation)
            .where(
                SessionTurn.session_id == session_id,
                SessionTurn.evaluation.is_not(None),
            )
            .order_by(SessionTurn.ordinal.desc())
            .limit(limit)
        )
    ).all()
    result: list[dict[str, float]] = []
    for row in reversed(rows):
        ev = row[0] or {}
        dims = ev.get("dimensions") or {}
        result.append(dims)
    return result


async def _upsert_weakness(
    session: AsyncSession,
    project_id: uuid.UUID,
    competency_id: uuid.UUID | None,
    updates: list[dict[str, Any]],
) -> None:
    for update in updates:
        stmt = select(WeaknessRecord).where(
            WeaknessRecord.project_id == project_id,
            WeaknessRecord.competency_id == competency_id,
            WeaknessRecord.dimension == update["dimension"],
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = WeaknessRecord(
                project_id=project_id,
                competency_id=competency_id,
                dimension=update["dimension"],
                severity=update["severity"],
                occurrences=1 if update["increment_occurrence"] else 0,
            )
            session.add(row)
        else:
            row.severity = update["severity"]
            if update["increment_occurrence"]:
                row.occurrences += 1
            row.last_seen = datetime.now(timezone.utc)


async def _recompute_readiness(
    session: AsyncSession,
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    source: str,
) -> ReadinessSnapshot:
    competencies = (
        await session.execute(
            select(CompetencyItem).where(CompetencyItem.project_id == project_id)
        )
    ).scalars().all()
    recent_dims = await _recent_scores(session, session_id, limit=12)
    weakness_rows = (
        await session.execute(
            select(WeaknessRecord).where(WeaknessRecord.project_id == project_id)
        )
    ).scalars().all()
    weakness_by_bucket: dict[str, float] = {}
    for w in weakness_rows:
        weakness_by_bucket[w.dimension] = max(weakness_by_bucket.get(w.dimension, 0.0), w.severity)
    difficulty_history = [
        row[0]
        for row in (
            await session.execute(
                select(SessionTurn.difficulty)
                .where(SessionTurn.session_id == session_id)
                .order_by(SessionTurn.ordinal.asc())
            )
        ).all()
    ]
    inputs = readiness_engine.ReadinessInputs(
        competency_mastery=[c.mastery for c in competencies],
        competency_attempts=[c.attempts for c in competencies],
        recent_dimension_scores=recent_dims,
        weakness_severity=weakness_by_bucket,
        difficulty_history=difficulty_history,
        total_competencies=len(competencies),
    )
    scores = readiness_engine.compute(inputs)
    return await _persist_snapshot(session, project_id, session_id, source, scores)


def _turn_to_response(turn: SessionTurn) -> TurnResponse:
    return TurnResponse.model_validate(turn)


# ─── project-scoped: start a new session ──────────────────────────────────


@project_router.post(
    "/",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    project_id: uuid.UUID,
    payload: SessionCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PreparationSession:
    project = await _load_owned_project(project_id, current, session)
    # Require at least one competency to keep questions grounded.
    has_comp = (
        await session.execute(
            select(CompetencyItem.id).where(CompetencyItem.project_id == project.id).limit(1)
        )
    ).first()
    if has_comp is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has no competency map — run POST /competencies/extract first.",
        )
    prep = PreparationSession(
        project_id=project.id,
        mode=payload.mode,
        difficulty=payload.difficulty,
    )
    session.add(prep)
    await session.commit()
    await session.refresh(prep)
    return prep


@project_router.get("/", response_model=list[SessionResponse])
async def list_sessions_for_project(
    project_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PreparationSession]:
    await _load_owned_project(project_id, current, session)
    rows = (
        await session.execute(
            select(PreparationSession)
            .where(PreparationSession.project_id == project_id)
            .order_by(PreparationSession.started_at.desc())
        )
    ).scalars().all()
    return list(rows)


# ─── session-scoped ───────────────────────────────────────────────────────


@router.get("/{session_id}", response_model=SessionWithTurns)
async def get_session_detail(
    session_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionWithTurns:
    prep, _ = await _load_owned_session(session_id, current, session)
    turns = (
        await session.execute(
            select(SessionTurn)
            .where(SessionTurn.session_id == prep.id)
            .order_by(SessionTurn.ordinal.asc())
        )
    ).scalars().all()
    return SessionWithTurns(
        **SessionResponse.model_validate(prep).model_dump(),
        turns=[_turn_to_response(t) for t in turns],
    )


@router.post(
    "/{session_id}/turns",
    response_model=TurnResponse,
    status_code=status.HTTP_201_CREATED,
)
async def next_turn(
    session_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TurnResponse:
    prep, project = await _load_owned_session(session_id, current, session)
    if prep.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Session is not active."
        )
    # Refuse to ask a new question while the previous turn is unanswered.
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
        return _turn_to_response(open_turn)

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

    agent = ExaminerAgent()
    result = await agent.execute(
        AgentContext(
            user_id=str(current.id),
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
    if result.status != "success":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.result.get("reason", "examiner failed"),
        )

    comp_id_raw = result.result.get("competency_id")
    turn = SessionTurn(
        session_id=prep.id,
        ordinal=next_ordinal,
        question=result.result["question"],
        topic=result.result["topic"],
        difficulty=result.result["difficulty"],
        competency_id=uuid.UUID(comp_id_raw) if comp_id_raw else None,
        grounding=result.result["grounding"],
    )
    session.add(turn)
    await session.commit()
    await session.refresh(turn)
    return _turn_to_response(turn)


@router.post(
    "/{session_id}/turns/{ordinal}/answer",
    response_model=TurnResponse,
)
async def submit_answer(
    session_id: uuid.UUID,
    ordinal: int,
    payload: TurnAnswer,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TurnResponse:
    prep, project = await _load_owned_session(session_id, current, session)
    if prep.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Session is not active."
        )
    turn = (
        await session.execute(
            select(SessionTurn).where(
                SessionTurn.session_id == prep.id,
                SessionTurn.ordinal == ordinal,
            )
        )
    ).scalar_one_or_none()
    if turn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn not found")
    if turn.user_answer is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Turn already answered."
        )

    grounding_text = await _grounding_text(session, turn.grounding)

    evaluator = EvaluatorAgent()
    ev_result = await evaluator.execute(
        AgentContext(
            user_id=str(current.id),
            project_id=str(project.id),
            session_id=str(prep.id),
            goal_type=project.goal_type,
            difficulty=turn.difficulty,
        ),
        tools={
            "answer": payload.answer,
            "topic": turn.topic or "",
            "grounding_text": grounding_text,
            "difficulty": turn.difficulty,
            "seconds_taken": payload.seconds_taken,
            "mode": prep.mode,
        },
    )
    if ev_result.status != "success":
        raise HTTPException(status_code=500, detail="evaluator failed")

    # Update competency mastery (running average).
    if turn.competency_id is not None:
        competency = await session.get(CompetencyItem, turn.competency_id)
        if competency is not None:
            competency.attempts += 1
            if ev_result.result["overall"] >= 0.7:
                competency.correct += 1
            weight = 1 / competency.attempts
            competency.mastery = round(
                (1 - weight) * competency.mastery + weight * ev_result.result["overall"],
                4,
            )

    # Weakness deltas.
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

    weakness_agent = WeaknessAgent()
    weakness_result = await weakness_agent.execute(
        AgentContext(
            user_id=str(current.id),
            project_id=str(project.id),
            session_id=str(prep.id),
        ),
        tools={
            "dimensions": ev_result.result["dimensions"],
            "current_severity": current_severity,
        },
    )
    await _upsert_weakness(
        session, project.id, turn.competency_id, weakness_result.result["updates"]
    )

    # Adaptive planner.
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

    planner = AdaptivePlannerAgent()
    plan_result = await planner.execute(
        AgentContext(
            user_id=str(current.id),
            project_id=str(project.id),
            session_id=str(prep.id),
            goal_type=project.goal_type,
            difficulty=turn.difficulty,
        ),
        tools={
            "overall": ev_result.result["overall"],
            "difficulty": turn.difficulty,
            "recent_scores": recent_overalls,
            "weakness_severity": max_severity,
            "mode": prep.mode,
            "topic": turn.topic or "",
            "turns_taken": len(turns_so_far),
            "max_turns": 10 if prep.mode == "final_boss" else 8,
        },
    )

    coach_note: str | None = plan_result.result.get("coach_note")
    if plan_result.result["action"] == "coach_intervention":
        coach_agent = CoachAgent()
        # Pick weakest dimension bucket for the hint.
        weakest = min(
            ev_result.result["dimensions"].items(),
            key=lambda kv: kv[1],
        )[0]
        coach_result = await coach_agent.execute(
            AgentContext(
                user_id=str(current.id),
                project_id=str(project.id),
                session_id=str(prep.id),
            ),
            tools={
                "mode": prep.mode,
                "weakest_dimension": {
                    "accuracy": "knowledge",
                    "completeness": "knowledge",
                    "relevance": "knowledge",
                    "communication": "communication",
                    "conciseness": "communication",
                    "evidence": "evidence",
                    "response_time": "pressure",
                }.get(weakest, "knowledge"),
                "topic": turn.topic or "",
            },
        )
        if coach_result.result.get("note"):
            coach_note = coach_result.result["note"]

    now = datetime.now(timezone.utc)
    turn.user_answer = payload.answer
    turn.evaluation = ev_result.result
    turn.adaptive_action = plan_result.result
    turn.coach_note = coach_note
    turn.answered_at = now

    prep.difficulty = plan_result.result["next_difficulty"]

    await session.commit()

    # Recompute readiness after each answered turn.
    await _recompute_readiness(session, project.id, prep.id, source="turn")

    await session.refresh(turn)
    return _turn_to_response(turn)


@router.post("/{session_id}/finish", response_model=SessionWithTurns)
async def finish_session(
    session_id: uuid.UUID,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionWithTurns:
    prep, project = await _load_owned_session(session_id, current, session)
    if prep.status != "active":
        # Idempotent — return current state.
        turns = (
            await session.execute(
                select(SessionTurn)
                .where(SessionTurn.session_id == prep.id)
                .order_by(SessionTurn.ordinal.asc())
            )
        ).scalars().all()
        return SessionWithTurns(
            **SessionResponse.model_validate(prep).model_dump(),
            turns=[_turn_to_response(t) for t in turns],
        )

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
        "final_scores": {
            "knowledge": snapshot.knowledge,
            "communication": snapshot.communication,
            "evidence": snapshot.evidence,
            "conciseness": snapshot.conciseness,
            "pressure": snapshot.pressure,
            "consistency": snapshot.consistency,
            "coverage": snapshot.coverage,
        },
        "mode": prep.mode,
    }
    await session.commit()
    await session.refresh(prep)

    return SessionWithTurns(
        **SessionResponse.model_validate(prep).model_dump(),
        turns=[_turn_to_response(t) for t in turns],
    )
