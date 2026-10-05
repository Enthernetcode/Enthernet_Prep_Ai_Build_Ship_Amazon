"""Admin endpoints for platform-wide configuration.

Currently manages provider configs, SMTP config, and site-wide announcements.
Access is gated by `settings.admin_emails` (case-insensitive). Non-admins get 403.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.db import get_session
from app.mail import MailMessage, SmtpNotConfigured, send_mail
from app.models.announcement import Announcement
from app.models.provider_config import ProviderConfig
from app.models.smtp_config import SmtpConfig
from app.models.user import User
from app.schemas.admin import (
    AnnouncementCreate,
    AnnouncementResponse,
    ProviderConfigResponse,
    ProviderConfigUpdate,
    SmtpConfigResponse,
    SmtpConfigUpdate,
    SmtpTestRequest,
)

router = APIRouter()

_EDITABLE_SCOPES = {"lab"}
_ALL_SCOPES = {"lab", "judged"}


def is_admin_email(email: str) -> bool:
    if not settings.admin_emails:
        return False
    normalised = {e.strip().lower() for e in settings.admin_emails if e.strip()}
    return email.lower() in normalised


async def require_admin(
    current: Annotated[User, Depends(get_current_user)],
) -> User:
    if not is_admin_email(current.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current


# ─── Providers ───────────────────────────────────────────────────────────────


def _provider_to_response(row: ProviderConfig) -> ProviderConfigResponse:
    return ProviderConfigResponse(
        id=row.id,
        scope=row.scope,
        llm_provider=row.llm_provider,
        llm_model=row.llm_model,
        embedding_provider=row.embedding_provider,
        embedding_model=row.embedding_model,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
        editable=row.scope in _EDITABLE_SCOPES,
    )


@router.get("/providers", response_model=list[ProviderConfigResponse])
async def list_provider_configs(
    _: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProviderConfigResponse]:
    rows = (
        await session.execute(
            select(ProviderConfig).order_by(ProviderConfig.scope.asc())
        )
    ).scalars().all()
    return [_provider_to_response(r) for r in rows]


@router.get("/providers/{scope}", response_model=ProviderConfigResponse)
async def get_provider_config(
    scope: str,
    _: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderConfigResponse:
    if scope not in _ALL_SCOPES:
        raise HTTPException(status_code=404, detail="Unknown scope")
    row = (
        await session.execute(
            select(ProviderConfig).where(ProviderConfig.scope == scope)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Scope not configured")
    return _provider_to_response(row)


@router.put("/providers/{scope}", response_model=ProviderConfigResponse)
async def update_provider_config(
    scope: str,
    payload: ProviderConfigUpdate,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderConfigResponse:
    if scope not in _EDITABLE_SCOPES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Scope {scope!r} is read-only. Only {sorted(_EDITABLE_SCOPES)} "
                "can be edited via this API."
            ),
        )
    row = (
        await session.execute(
            select(ProviderConfig).where(ProviderConfig.scope == scope)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Scope not configured")
    row.llm_provider = payload.llm_provider
    row.llm_model = payload.llm_model
    row.embedding_provider = payload.embedding_provider
    row.embedding_model = payload.embedding_model
    row.updated_by = admin.id
    await session.commit()
    await session.refresh(row)
    return _provider_to_response(row)


# ─── SMTP ────────────────────────────────────────────────────────────────────


async def _load_smtp_row(session: AsyncSession) -> SmtpConfig:
    row = (
        await session.execute(select(SmtpConfig).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = SmtpConfig()
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


def _smtp_to_response(row: SmtpConfig) -> SmtpConfigResponse:
    return SmtpConfigResponse(
        id=row.id,
        enabled=row.enabled,
        host=row.host,
        port=row.port,
        username=row.username,
        from_address=row.from_address,
        from_name=row.from_name,
        use_tls=row.use_tls,
        use_starttls=row.use_starttls,
        updated_at=row.updated_at,
        password_set=bool(row.password),
    )


@router.get("/smtp", response_model=SmtpConfigResponse)
async def get_smtp_config(
    _: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SmtpConfigResponse:
    row = await _load_smtp_row(session)
    return _smtp_to_response(row)


@router.put("/smtp", response_model=SmtpConfigResponse)
async def update_smtp_config(
    payload: SmtpConfigUpdate,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SmtpConfigResponse:
    row = await _load_smtp_row(session)
    row.enabled = payload.enabled
    row.host = payload.host.strip()
    row.port = payload.port
    row.username = payload.username.strip()
    if payload.password:
        row.password = payload.password
    row.from_address = payload.from_address.strip()
    row.from_name = payload.from_name.strip() or "Enthernet Prep AI"
    row.use_tls = payload.use_tls
    row.use_starttls = payload.use_starttls
    row.updated_by = admin.id
    await session.commit()
    await session.refresh(row)
    return _smtp_to_response(row)


@router.post("/smtp/test", status_code=status.HTTP_202_ACCEPTED)
async def send_smtp_test(
    payload: SmtpTestRequest,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    try:
        await send_mail(
            session,
            MailMessage(
                to=payload.to,
                subject="Enthernet Prep AI — SMTP test",
                text=(
                    "This is a test email sent from Enthernet Prep AI's admin "
                    f"panel by {admin.email}. If you can read this, outbound "
                    "email is working."
                ),
                html=(
                    "<p>This is a test email sent from Enthernet Prep AI's "
                    f"admin panel by <b>{admin.email}</b>. If you can read "
                    "this, outbound email is working.</p>"
                ),
            ),
        )
    except SmtpNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SMTP error: {exc}") from None
    return {"status": "sent", "to": payload.to}


# ─── Announcements ───────────────────────────────────────────────────────────


def _ann_to_response(row: Announcement) -> AnnouncementResponse:
    return AnnouncementResponse(
        id=row.id,
        title=row.title,
        body=row.body,
        kind=row.kind,
        audience=row.audience,
        active=row.active,
        expires_at=row.expires_at,
        created_at=row.created_at,
        created_by=row.created_by,
    )


@router.get("/announcements", response_model=list[AnnouncementResponse])
async def list_announcements(
    _: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AnnouncementResponse]:
    rows = (
        await session.execute(
            select(Announcement).order_by(Announcement.created_at.desc())
        )
    ).scalars().all()
    return [_ann_to_response(r) for r in rows]


@router.post(
    "/announcements",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_announcement(
    payload: AnnouncementCreate,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnnouncementResponse:
    row = Announcement(
        title=payload.title,
        body=payload.body,
        kind=payload.kind,
        audience=payload.audience,
        active=payload.active,
        expires_at=payload.expires_at,
        created_by=admin.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _ann_to_response(row)


@router.delete(
    "/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_announcement(
    announcement_id: uuid.UUID,
    _: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = await session.get(Announcement, announcement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    await session.delete(row)
    await session.commit()
