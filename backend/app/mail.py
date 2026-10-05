"""Outbound email service.

Reads config from the `smtp_configs` DB row (populated via admin UI) and
sends a transactional email using `aiosmtplib`. Silently no-ops when SMTP is
not yet configured — the caller decides whether to surface that.
"""
from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.smtp_config import SmtpConfig


class SmtpNotConfigured(Exception):
    """Mail cannot be sent because the admin hasn't populated SMTP config."""


@dataclass
class MailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


async def load_smtp_config(session: AsyncSession) -> SmtpConfig | None:
    return (
        await session.execute(select(SmtpConfig).limit(1))
    ).scalar_one_or_none()


async def send_mail(session: AsyncSession, message: MailMessage) -> None:
    cfg = await load_smtp_config(session)
    if cfg is None or not cfg.enabled or not cfg.host or not cfg.from_address:
        raise SmtpNotConfigured(
            "SMTP is not configured yet. Ask an admin to open /admin, enter "
            "the mail server details, and enable outbound email."
        )

    envelope = EmailMessage()
    from_name = cfg.from_name or "Enthernet Prep AI"
    envelope["From"] = f"{from_name} <{cfg.from_address}>"
    envelope["To"] = message.to
    envelope["Subject"] = message.subject
    envelope.set_content(message.text)
    if message.html:
        envelope.add_alternative(message.html, subtype="html")

    kwargs: dict = {
        "hostname": cfg.host,
        "port": cfg.port,
        "start_tls": cfg.use_starttls and not cfg.use_tls,
        "use_tls": cfg.use_tls and not cfg.use_starttls,
    }
    if cfg.username:
        kwargs["username"] = cfg.username
        kwargs["password"] = cfg.password

    await aiosmtplib.send(envelope, **kwargs)
