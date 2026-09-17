from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import db as app_db
from app.config import settings

# WSL2 clock in this dev env jumps forward mid-suite (multi-hour deltas).
# With the default 60-min JWT window, tokens minted in test N get rejected
# as expired by test N+1. Crank it up so tests are immune to host clock drift.
settings.jwt_access_token_minutes = 60 * 24 * 30  # 30 days

# Rebind the module-level engine + sessionmaker BEFORE the app is imported.
# NullPool eliminates the async-pool state carryover that made auth tests
# flaky under a session-scoped event loop (see memory: feedback_test_isolation).
_test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)
app_db.engine = _test_engine
app_db.AsyncSessionLocal = _TestSessionLocal

from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:8]}@example.com"
