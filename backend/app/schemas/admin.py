from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


ProviderName = Literal["mock", "openai", "bedrock"]


class ProviderConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope: str
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    updated_at: datetime
    updated_by: uuid.UUID | None
    editable: bool = False


class ProviderConfigUpdate(BaseModel):
    llm_provider: ProviderName
    llm_model: str = Field(min_length=1, max_length=128)
    embedding_provider: ProviderName
    embedding_model: str = Field(min_length=1, max_length=128)


class SmtpConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    enabled: bool
    host: str
    port: int
    username: str
    from_address: str
    from_name: str
    use_tls: bool
    use_starttls: bool
    updated_at: datetime
    password_set: bool = False


class SmtpConfigUpdate(BaseModel):
    enabled: bool = False
    host: str = Field(default="", max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=255)
    # Empty string means "keep existing" so the admin form doesn't need to
    # re-type the password on every save.
    password: str = Field(default="", max_length=512)
    from_address: str = Field(default="", max_length=320)
    from_name: str = Field(default="Enthernet Prep AI", max_length=255)
    use_tls: bool = True
    use_starttls: bool = True


class SmtpTestRequest(BaseModel):
    to: EmailStr


AnnouncementKindLiteral = Literal["info", "warning", "success"]
AnnouncementAudience = Literal["all", "admins"]


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    kind: AnnouncementKindLiteral = "info"
    audience: AnnouncementAudience = "all"
    expires_at: datetime | None = None
    active: bool = True


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    kind: str
    audience: str
    active: bool
    expires_at: datetime | None
    created_at: datetime
    created_by: uuid.UUID | None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=8, max_length=200)
    password: str = Field(min_length=8, max_length=128)
