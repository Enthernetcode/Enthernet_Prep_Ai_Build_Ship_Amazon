from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import is_admin_email
from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.config import settings
from app.db import get_session
from app.mail import MailMessage, SmtpNotConfigured, send_mail
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.schemas.admin import ForgotPasswordRequest, ResetPasswordRequest
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter()

_RESET_TOKEN_TTL_MINUTES = 30


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        is_admin=is_admin_email(user.email),
    )


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
    await session.refresh(user)
    return _user_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
async def me(current: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return _user_response(current)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Send a password reset link if the email exists. Same body regardless
    so we don't leak account existence to enumerators."""
    user = (
        await session.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()

    generic_ok = {
        "status": "sent",
        "detail": "If the email is registered, a reset link has been sent.",
    }
    if user is None:
        return generic_ok

    plain = secrets.token_urlsafe(32)
    row = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(plain),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=_RESET_TOKEN_TTL_MINUTES),
    )
    session.add(row)
    await session.commit()

    reset_url = f"{settings.public_web_base_url}/reset-password/{plain}"
    body_text = (
        "Hi,\n\nSomeone (hopefully you) asked to reset the password for your "
        "Enthernet Prep AI account.\n\nOpen this link within "
        f"{_RESET_TOKEN_TTL_MINUTES} minutes to choose a new password:\n\n"
        f"{reset_url}\n\nIf you didn't request this, ignore this email — "
        "your password stays the same."
    )
    body_html = (
        "<p>Hi,</p>"
        "<p>Someone (hopefully you) asked to reset the password for your "
        "Enthernet Prep AI account.</p>"
        f'<p><a href="{reset_url}">Choose a new password</a> (link valid for '
        f"{_RESET_TOKEN_TTL_MINUTES} minutes).</p>"
        "<p>If you didn't request this, ignore this email — your password "
        "stays the same.</p>"
    )
    try:
        await send_mail(
            session,
            MailMessage(
                to=user.email,
                subject="Reset your Enthernet Prep AI password",
                text=body_text,
                html=body_html,
            ),
        )
    except SmtpNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return generic_ok


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    row = (
        await session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == _hash_token(payload.token)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=400, detail="Invalid or already-used token")
    if row.used_at is not None:
        raise HTTPException(status_code=400, detail="Token already used")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expired")

    user = await session.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Account no longer exists")
    user.password_hash = hash_password(payload.password)
    row.used_at = datetime.now(timezone.utc)
    await session.commit()
    return {"status": "reset"}
