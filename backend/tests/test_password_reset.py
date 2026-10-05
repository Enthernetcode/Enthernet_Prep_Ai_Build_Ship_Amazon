from __future__ import annotations

import hashlib
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.password_reset import PasswordResetToken
from app.models.user import User


PASSWORD = "hunter2hunter2"


async def _register(client: AsyncClient, email: str) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )


async def _read_token_for_user(email: str) -> str | None:
    """Peek at the DB to find the plaintext token by hash-matching. The
    forgot-password endpoint stores only the hash, so tests can't retrieve
    the plaintext directly — instead we generate a token ourselves later
    when verifying reset."""
    async with AsyncSessionLocal() as s:
        u = (
            await s.execute(select(User).where(User.email == email.lower()))
        ).scalar_one_or_none()
        if u is None:
            return None
        row = (
            await s.execute(
                select(PasswordResetToken)
                .where(PasswordResetToken.user_id == u.id)
                .order_by(PasswordResetToken.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return row.token_hash if row else None


@pytest.mark.asyncio
async def test_forgot_password_generic_on_unknown_email(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "sent"
    # No token created, no crash.


@pytest.mark.asyncio
async def test_forgot_password_without_smtp_returns_503(
    client: AsyncClient,
) -> None:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    await _register(client, email)
    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"email": email}
    )
    # Without SMTP configured, we surface a 503 so the user knows to contact
    # the admin (rather than silently swallowing the request).
    assert resp.status_code == 503
    assert "SMTP" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reset_password_rejects_invalid_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "password": "new-password-2026"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_changes_password_and_burns_token(
    client: AsyncClient,
) -> None:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    await _register(client, email)
    # Insert a token directly (avoiding SMTP dependency). Unique per run so
    # rerunning against the same DB doesn't trip the unique constraint.
    plain = f"plaintext-token-{uuid.uuid4().hex}"
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    async with AsyncSessionLocal() as s:
        u = (
            await s.execute(select(User).where(User.email == email.lower()))
        ).scalar_one()
        from datetime import datetime, timedelta, timezone

        row = PasswordResetToken(
            user_id=u.id,
            token_hash=hashed,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        s.add(row)
        await s.commit()

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": plain, "password": "brand-new-password"},
    )
    assert reset.status_code == 200

    # Old password no longer works.
    old = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert old.status_code == 401

    # New password works.
    new = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "brand-new-password"},
    )
    assert new.status_code == 200

    # Second reset with same token fails.
    replay = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": plain, "password": "yet-another"},
    )
    assert replay.status_code == 400
