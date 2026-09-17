from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.user import User

_hasher = PasswordHasher()
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def create_access_token(subject: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.app_secret, algorithm=settings.jwt_algorithm)


async def get_current_user(
    token: Annotated[str, Depends(_oauth2)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    def _fail(reason: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {reason}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token, settings.app_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise _fail(f"jwt:{exc}") from None

    sub = payload.get("sub")
    if sub is None:
        raise _fail("sub-missing")
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise _fail("sub-not-uuid") from None

    user = await session.get(User, user_id)
    if user is None:
        raise _fail(f"user-not-found:{user_id}")
    return user
