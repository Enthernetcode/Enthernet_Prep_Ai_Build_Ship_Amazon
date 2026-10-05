from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.config import settings


PASSWORD = "hunter2hunter2"


async def _register_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return resp.json()["access_token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_smtp_response_never_includes_password(
    client: AsyncClient, monkeypatch
) -> None:
    admin_email = f"a-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "admin_emails", [admin_email])
    token = await _register_login(client, admin_email)

    resp = await client.get("/api/v1/admin/smtp", headers=_hdr(token))
    assert resp.status_code == 200
    body = resp.json()
    # Password is never sent to the client. `password_set` is the only
    # signal about whether one is stored.
    assert "password" not in body
    assert "password_set" in body


@pytest.mark.asyncio
async def test_admin_can_update_smtp_and_password_persistence(
    client: AsyncClient, monkeypatch
) -> None:
    admin_email = f"a-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "admin_emails", [admin_email])
    token = await _register_login(client, admin_email)

    put1 = await client.put(
        "/api/v1/admin/smtp",
        headers=_hdr(token),
        json={
            "enabled": True,
            "host": "smtp.example.com",
            "port": 465,
            "username": "user",
            "password": "s3cret",
            "from_address": "hi@example.com",
            "from_name": "Prep AI",
            "use_tls": True,
            "use_starttls": False,
        },
    )
    assert put1.status_code == 200
    assert put1.json()["password_set"] is True
    assert put1.json()["host"] == "smtp.example.com"

    # Empty password on a subsequent PUT must preserve the existing one.
    put2 = await client.put(
        "/api/v1/admin/smtp",
        headers=_hdr(token),
        json={
            "enabled": True,
            "host": "smtp.example.com",
            "port": 465,
            "username": "user",
            "password": "",  # keep-existing signal
            "from_address": "hi@example.com",
            "from_name": "Prep AI",
            "use_tls": True,
            "use_starttls": False,
        },
    )
    assert put2.status_code == 200
    assert put2.json()["password_set"] is True


@pytest.mark.asyncio
async def test_smtp_test_email_reports_not_configured(
    client: AsyncClient, monkeypatch
) -> None:
    admin_email = f"a-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "admin_emails", [admin_email])
    token = await _register_login(client, admin_email)

    # Ensure SMTP is disabled.
    await client.put(
        "/api/v1/admin/smtp",
        headers=_hdr(token),
        json={
            "enabled": False,
            "host": "",
            "port": 587,
            "username": "",
            "password": "",
            "from_address": "",
            "from_name": "Prep AI",
            "use_tls": True,
            "use_starttls": True,
        },
    )
    resp = await client.post(
        "/api/v1/admin/smtp/test",
        headers=_hdr(token),
        json={"to": "someone@example.com"},
    )
    assert resp.status_code == 409
    assert "SMTP" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_announcements_admin_crud_and_public_read(
    client: AsyncClient, monkeypatch
) -> None:
    admin_email = f"a-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "admin_emails", [admin_email])
    admin_token = await _register_login(client, admin_email)
    user_token = await _register_login(
        client, f"u-{uuid.uuid4().hex[:8]}@example.com"
    )

    # Admin creates an announcement targeted at "all"
    create = await client.post(
        "/api/v1/admin/announcements",
        headers=_hdr(admin_token),
        json={
            "title": "Scheduled maintenance",
            "body": "We'll be down briefly on Saturday.",
            "kind": "info",
            "audience": "all",
        },
    )
    assert create.status_code == 201
    ann_id = create.json()["id"]

    # Public list (as a regular user)
    listing = await client.get(
        "/api/v1/announcements/", headers=_hdr(user_token)
    )
    assert listing.status_code == 200
    assert any(a["id"] == ann_id for a in listing.json())

    # Admin creates an admins-only announcement
    admins_only = await client.post(
        "/api/v1/admin/announcements",
        headers=_hdr(admin_token),
        json={
            "title": "Rotate keys",
            "body": "Time to rotate provider keys.",
            "audience": "admins",
        },
    )
    admins_only_id = admins_only.json()["id"]
    user_listing = await client.get(
        "/api/v1/announcements/", headers=_hdr(user_token)
    )
    assert not any(a["id"] == admins_only_id for a in user_listing.json())

    admin_listing = await client.get(
        "/api/v1/announcements/", headers=_hdr(admin_token)
    )
    assert any(a["id"] == admins_only_id for a in admin_listing.json())

    # Delete
    delete = await client.delete(
        f"/api/v1/admin/announcements/{ann_id}", headers=_hdr(admin_token)
    )
    assert delete.status_code == 204
