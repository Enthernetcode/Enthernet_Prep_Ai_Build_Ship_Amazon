"""Public announcements — the site-wide banner data source."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import is_admin_email
from app.auth import get_current_user
from app.db import get_session
from app.models.announcement import Announcement
from app.models.user import User
from app.schemas.admin import AnnouncementResponse

router = APIRouter()


def _to_response(row: Announcement) -> AnnouncementResponse:
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


@router.get("/", response_model=list[AnnouncementResponse])
async def list_active_announcements(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AnnouncementResponse]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(Announcement)
        .where(
            Announcement.active.is_(True),
            or_(
                Announcement.expires_at.is_(None),
                Announcement.expires_at > now,
            ),
        )
        .order_by(Announcement.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not is_admin_email(current.email):
        rows = [r for r in rows if r.audience == "all"]
    return [_to_response(r) for r in rows]
