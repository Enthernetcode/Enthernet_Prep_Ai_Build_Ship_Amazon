from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import storage
from app.api.v1.router import router as v1_router
from app.config import settings

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.ensure_bucket()
    yield


app = FastAPI(
    title="Enthernet Prep AI",
    version="0.0.1",
    description="Agentic AI readiness engine. Live in the Moment.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "eprep-backend", "status": "ok"}
