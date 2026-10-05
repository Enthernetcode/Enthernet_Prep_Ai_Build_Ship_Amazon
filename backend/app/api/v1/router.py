from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    alexa,
    announcements,
    auth,
    competencies,
    demo,
    documents,
    health,
    projects,
    readiness,
    retrieval,
    sessions,
)

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(projects.router, prefix="/projects", tags=["projects"])
router.include_router(
    documents.project_router,
    prefix="/projects/{project_id}/documents",
    tags=["documents"],
)
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(
    retrieval.router,
    prefix="/projects/{project_id}/retrieve",
    tags=["retrieval"],
)
router.include_router(
    competencies.router,
    prefix="/projects/{project_id}/competencies",
    tags=["competencies"],
)
router.include_router(
    readiness.router,
    prefix="/projects/{project_id}/readiness",
    tags=["readiness"],
)
router.include_router(
    sessions.project_router,
    prefix="/projects/{project_id}/sessions",
    tags=["sessions"],
)
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
router.include_router(alexa.router, prefix="/alexa", tags=["alexa"])
router.include_router(demo.router, prefix="/demo", tags=["demo"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(
    announcements.router, prefix="/announcements", tags=["announcements"]
)
