"""Second MCP server for experimentation.

Mounted at `/api/v1/mcp-lab/`. Mirrors the judged server's 7 `prep.*` tools by
delegating to their functions in `app.mcp.server` — no behavior change for the
existing tool set. Adds one extra tool, `prep.debug.resolve_provider`, that
returns whatever the per-request resolver would have selected. That's the
smallest possible proof that the plumbing works; real LLM-using tools can
plug in later.

Nothing in this module can affect the judged path.
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.db import AsyncSessionLocal
from app.mcp import server as judged
from app.providers.router import resolve_providers


lab_server = MCPServer(
    name="enthernet-prep-ai-lab",
    version="0.1.0",
    instructions=(
        "Experimental MCP surface for Enthernet Prep AI. Same seven prep.* "
        "tools as the judged endpoint at /api/v1/mcp/, plus a debug tool to "
        "inspect per-request provider resolution. Callers may set "
        "`X-LLM-Provider` (mock | openai | bedrock) to override the admin-"
        "configured default for a single tool call."
    ),
)


# ─── Re-register the 7 judged tools verbatim ────────────────────────────────


@lab_server.tool(
    name="prep.list_projects",
    title="List preparation projects",
    description=(
        "Return the authenticated user's preparation projects, newest first. "
        "Same behavior as the judged endpoint — safe to use interchangeably."
    ),
)
async def list_projects(ctx: Context) -> dict[str, Any]:
    return await judged.list_projects(ctx)


@lab_server.tool(
    name="prep.extract_competencies",
    title="Extract competencies from uploaded documents",
    description=(
        "Run the Knowledge Extraction Agent over every processed chunk in the "
        "given project. Same behavior as the judged endpoint."
    ),
)
async def extract_competencies(ctx: Context, project_id: str) -> dict[str, Any]:
    return await judged.extract_competencies(ctx, project_id)


@lab_server.tool(
    name="prep.get_readiness",
    title="Get the latest readiness snapshot",
    description="Return the latest deterministic readiness snapshot for a project.",
)
async def get_readiness(ctx: Context, project_id: str) -> dict[str, Any]:
    return await judged.get_readiness(ctx, project_id)


@lab_server.tool(
    name="prep.start_session",
    title="Start a preparation session",
    description="Begin a mock_interview or final_boss session for a project.",
)
async def start_session(
    ctx: Context,
    project_id: str,
    mode: str = "mock_interview",
    difficulty: int = 3,
) -> dict[str, Any]:
    return await judged.start_session(ctx, project_id, mode, difficulty)


@lab_server.tool(
    name="prep.next_question",
    title="Ask the examiner for the next question",
    description="Generate the next grounded question for the session (idempotent within a turn).",
)
async def next_question(ctx: Context, session_id: str) -> dict[str, Any]:
    return await judged.next_question(ctx, session_id)


@lab_server.tool(
    name="prep.submit_answer",
    title="Submit an answer for evaluation",
    description="Evaluate the user's answer to the current turn and return next-step guidance.",
)
async def submit_answer(
    ctx: Context,
    session_id: str,
    ordinal: int,
    answer: str,
    seconds_taken: float | None = None,
) -> dict[str, Any]:
    return await judged.submit_answer(ctx, session_id, ordinal, answer, seconds_taken)


@lab_server.tool(
    name="prep.finish_session",
    title="Finish the session and get the final readiness report",
    description="Mark the session complete and compute the final readiness snapshot.",
)
async def finish_session(ctx: Context, session_id: str) -> dict[str, Any]:
    return await judged.finish_session(ctx, session_id)


# ─── Lab-only: provider resolution diagnostic ───────────────────────────────


@lab_server.tool(
    name="prep.debug.resolve_provider",
    title="Debug: show which provider the lab would use for this request",
    description=(
        "Returns the LLM and embedding provider/model the lab resolver picked "
        "for this call, and the source of the decision (header / db / "
        "settings). Handy for verifying that admin-configured defaults are "
        "live and that the `X-LLM-Provider` header override works. This tool "
        "does not call any external API."
    ),
)
async def debug_resolve_provider(ctx: Context) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        resolved = await resolve_providers(ctx, session, scope="lab")
    return {
        "llm_provider": resolved.llm_name,
        "llm_model": resolved.llm_model,
        "embedding_provider": resolved.embedding_name,
        "embedding_model": resolved.embedding_model,
        "source": resolved.source,
    }


def build_lab_mcp_asgi_app():
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=["*"],
        allowed_origins=["*"],
    )
    return lab_server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        transport_security=security,
    )
