"""§31–§33 Alexa+ webhook.

Maps Alexa intents onto the same session engine the web UI uses. The Alexa
account-linking access token is treated as a Bearer token and validated against
our JWT — so the same `get_current_user` guard applies. Request-signature
verification is intentionally stubbed for the demo; enable before submitting to
Amazon (see docs/alexa-integration.md).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sessions import (
    _competency_candidates,
    _grounding_text,
    _recent_scores,
    _recompute_readiness,
    _upsert_weakness,
)
from app.agents.adaptive import AdaptivePlannerAgent
from app.agents.base import AgentContext
from app.agents.evaluator import EvaluatorAgent
from app.agents.examiner import ExaminerAgent
from app.agents.weakness import WeaknessAgent
from app.auth import get_current_user
from app.db import get_session
from app.models.competency import CompetencyItem
from app.models.project import PreparationProject
from app.models.session import PreparationSession, SessionTurn
from app.models.user import User
from app.models.weakness import WeaknessRecord
from app.schemas.alexa import AlexaRequest, AlexaResponse

router = APIRouter()


def _speak(text: str, *, end: bool = False, reprompt: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "outputSpeech": {"type": "PlainText", "text": text},
        "shouldEndSession": end,
    }
    if reprompt and not end:
        body["reprompt"] = {
            "outputSpeech": {"type": "PlainText", "text": reprompt}
        }
    return body


async def _current_alexa_user(
    authorization: Annotated[str | None, Header()] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> User:
    # Alexa passes the linked user's OAuth token in session.user.accessToken;
    # our web wrapper forwards it as `Authorization: Bearer <token>`.
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Alexa account linking is required.",
        )
    token = authorization.split(" ", 1)[1]
    return await get_current_user(token=token, session=session)


async def _latest_active_session(
    session: AsyncSession, user: User, project_id: uuid.UUID | None = None
) -> tuple[PreparationSession, PreparationProject] | None:
    stmt = (
        select(PreparationSession, PreparationProject)
        .join(
            PreparationProject,
            PreparationProject.id == PreparationSession.project_id,
        )
        .where(
            PreparationProject.user_id == user.id,
            PreparationSession.status == "active",
        )
        .order_by(PreparationSession.started_at.desc())
        .limit(1)
    )
    if project_id is not None:
        stmt = stmt.where(PreparationSession.project_id == project_id)
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return row[0], row[1]


async def _pending_turn(
    session: AsyncSession, prep: PreparationSession
) -> SessionTurn | None:
    return (
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


async def _emit_next_question(
    session: AsyncSession,
    user: User,
    prep: PreparationSession,
    project: PreparationProject,
) -> SessionTurn:
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
    return turn


async def _handle_launch(
    session: AsyncSession, user: User
) -> AlexaResponse:
    projects = (
        await session.execute(
            select(PreparationProject)
            .where(PreparationProject.user_id == user.id)
            .order_by(PreparationProject.created_at.desc())
            .limit(3)
        )
    ).scalars().all()
    if not projects:
        return AlexaResponse(
            response=_speak(
                "You don't have any preparation projects yet. Create one on the web and come back.",
                end=True,
            )
        )
    names = ", ".join(p.name for p in projects)
    plural = "project" if len(projects) == 1 else "projects"
    return AlexaResponse(
        sessionAttributes={"projects": [str(p.id) for p in projects]},
        response=_speak(
            f"You have {len(projects)} active {plural}: {names}. Say 'start interview' to begin the first one.",
            reprompt="Say 'start interview' or 'final boss' to begin.",
        ),
    )


async def _handle_start(
    session: AsyncSession, user: User, mode: str
) -> AlexaResponse:
    project = (
        await session.execute(
            select(PreparationProject)
            .where(PreparationProject.user_id == user.id)
            .order_by(PreparationProject.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if project is None:
        return AlexaResponse(
            response=_speak("Create a preparation project on the web first.", end=True)
        )
    has_comp = (
        await session.execute(
            select(CompetencyItem.id)
            .where(CompetencyItem.project_id == project.id)
            .limit(1)
        )
    ).first()
    if has_comp is None:
        return AlexaResponse(
            response=_speak(
                "Your project has no competency map yet. Upload your CV and job description and try again.",
                end=True,
            )
        )
    prep = PreparationSession(
        project_id=project.id, mode=mode, difficulty=3 if mode != "final_boss" else 5
    )
    session.add(prep)
    await session.commit()
    await session.refresh(prep)
    turn = await _emit_next_question(session, user, prep, project)
    return AlexaResponse(
        sessionAttributes={"session_id": str(prep.id), "ordinal": turn.ordinal},
        response=_speak(turn.question, reprompt="Take your time. When you are ready, answer."),
    )


async def _handle_answer(
    session: AsyncSession,
    user: User,
    request_session_attrs: dict[str, Any],
    answer_text: str,
) -> AlexaResponse:
    session_id_raw = request_session_attrs.get("session_id")
    if not session_id_raw:
        found = await _latest_active_session(session, user)
        if found is None:
            return AlexaResponse(
                response=_speak(
                    "You don't have an active interview. Say 'start interview' to begin.",
                    reprompt="Say 'start interview'.",
                )
            )
        prep, project = found
    else:
        prep = await session.get(PreparationSession, uuid.UUID(session_id_raw))
        if prep is None:
            return AlexaResponse(
                response=_speak("That session was not found.", end=True)
            )
        project = await session.get(PreparationProject, prep.project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    turn = await _pending_turn(session, prep)
    if turn is None:
        # No pending question — ask a new one.
        turn = await _emit_next_question(session, user, prep, project)
        return AlexaResponse(
            sessionAttributes={"session_id": str(prep.id), "ordinal": turn.ordinal},
            response=_speak(turn.question),
        )

    grounding_text = await _grounding_text(session, turn.grounding)
    evaluator = EvaluatorAgent()
    ev_result = await evaluator.execute(
        AgentContext(
            user_id=str(user.id),
            project_id=str(project.id),
            session_id=str(prep.id),
            goal_type=project.goal_type,
            difficulty=turn.difficulty,
        ),
        tools={
            "answer": answer_text,
            "topic": turn.topic or "",
            "grounding_text": grounding_text,
            "difficulty": turn.difficulty,
            "seconds_taken": None,
            "mode": prep.mode,
        },
    )

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
            "dimensions": ev_result.result["dimensions"],
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
    plan_result = await AdaptivePlannerAgent().execute(
        AgentContext(
            user_id=str(user.id),
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
            "max_turns": 10 if prep.mode == "final_boss" else 6,
        },
    )
    now = datetime.now(timezone.utc)
    turn.user_answer = answer_text
    turn.evaluation = ev_result.result
    turn.adaptive_action = plan_result.result
    turn.coach_note = plan_result.result.get("coach_note")
    turn.answered_at = now
    prep.difficulty = plan_result.result["next_difficulty"]
    await session.commit()
    snapshot = await _recompute_readiness(session, project.id, prep.id, source="turn")

    if plan_result.result["should_finish"]:
        prep.status = "completed"
        prep.completed_at = now
        prep.summary = {
            "turns_answered": len(turns_so_far),
            "final_readiness": snapshot.overall,
            "mode": prep.mode,
        }
        await session.commit()
        pct = round(snapshot.overall * 100)
        speech = f"Interview complete. Your readiness is {pct} percent."
        return AlexaResponse(
            sessionAttributes={},
            response=_speak(speech, end=True),
        )

    next_turn = await _emit_next_question(session, user, prep, project)
    pct = round(snapshot.overall * 100)
    header = f"Noted. Readiness now {pct} percent. Next question."
    return AlexaResponse(
        sessionAttributes={"session_id": str(prep.id), "ordinal": next_turn.ordinal},
        response=_speak(f"{header} {next_turn.question}"),
    )


@router.post("", response_model=AlexaResponse)
@router.post("/", response_model=AlexaResponse)
async def alexa_webhook(
    payload: AlexaRequest,
    authorization: Annotated[str | None, Header()] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> AlexaResponse:
    user = await _current_alexa_user(authorization=authorization, session=session)
    request = payload.request or {}
    kind = request.get("type", "")
    session_attrs = payload.session.get("attributes", {}) if payload.session else {}

    if kind == "LaunchRequest":
        return await _handle_launch(session, user)
    if kind == "SessionEndedRequest":
        return AlexaResponse(response={"shouldEndSession": True})
    if kind == "IntentRequest":
        intent = request.get("intent", {}) or {}
        name = intent.get("name", "")
        slots = intent.get("slots", {}) or {}
        if name == "StartInterviewIntent":
            return await _handle_start(session, user, mode="mock_interview")
        if name == "FinalBossIntent":
            return await _handle_start(session, user, mode="final_boss")
        if name == "AnswerIntent":
            slot = slots.get("answer") or {}
            text = slot.get("value") or request.get("intent", {}).get("value") or ""
            if not text:
                return AlexaResponse(
                    response=_speak(
                        "I didn't catch that. Please answer the question.",
                        reprompt="Try again with your answer.",
                    )
                )
            return await _handle_answer(session, user, session_attrs, text)
        if name in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
            return AlexaResponse(response=_speak("Goodbye.", end=True))
        if name == "AMAZON.HelpIntent":
            return AlexaResponse(
                response=_speak(
                    "Say 'start interview' to practice, or 'final boss' for the graded assessment.",
                    reprompt="Say 'start interview'.",
                )
            )

    return AlexaResponse(
        response=_speak("Sorry, I couldn't process that request.", end=True)
    )
