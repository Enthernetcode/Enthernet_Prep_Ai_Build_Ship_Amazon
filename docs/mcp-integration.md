# MCP integration (Alexa+ track)

Enthernet Prep AI exposes its preparation engine as a **self-hosted MCP server** — the primary integration surface for the Alexa+ track of the Amazon Developer Hackathon.

- **Endpoint:** `POST /api/v1/mcp/`
- **Transport:** Streamable HTTP (MCP spec **2025-11-25**)
- **Auth:** `Authorization: Bearer <jwt>` (same JWT the web app uses; obtain via `POST /api/v1/auth/login`)
- **Session mode:** `stateless_http=True` so any Alexa+/MCP client can hit us without sticky-session concerns.

## Tools

| Tool | What it does |
|---|---|
| `prep.list_projects` | Return the user's preparation projects. |
| `prep.extract_competencies` | Run the Knowledge Extraction Agent over uploaded chunks + refresh baseline readiness. |
| `prep.get_readiness` | Latest deterministic readiness snapshot (7 dimensions + overall). |
| `prep.start_session` | Begin a `mock_interview` or `final_boss` session. |
| `prep.next_question` | Ask the Examiner for the next grounded question. Idempotent within a turn. |
| `prep.submit_answer` | Evaluate an answer, upsert weakness records, run the adaptive planner, recompute readiness. |
| `prep.finish_session` | Mark the session complete and return the final readiness report. |

Every tool wraps the same engine our REST API uses (`app/api/v1/sessions.py`) — no duplicated business logic. Changing the engine changes both surfaces at once.

## Connect from Claude Desktop

Add to your MCP client config:

```json
{
  "mcpServers": {
    "enthernet-prep-ai": {
      "type": "streamable-http",
      "url": "https://<your-tunnel>/api/v1/mcp/",
      "headers": {
        "Authorization": "Bearer <jwt-from-/auth/login>"
      }
    }
  }
}
```

Then in Claude: *"List my preparation projects. Start a mock interview on the Cloud Engineer one. Ask me the first question."*

## Try locally with `curl`

```bash
# 1. Seed a demo user + project + docs + baseline (dev-only endpoint):
curl -X POST http://localhost:8000/api/v1/demo/seed -H 'Content-Type: application/json'
# → returns { access_token, project_id, ... }

# 2. Initialize the MCP session:
export TOKEN=<paste access_token>
curl -sS -X POST http://localhost:8000/api/v1/mcp/ \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{
           "protocolVersion":"2025-11-25","capabilities":{},
           "clientInfo":{"name":"curl","version":"1"}}}'
# → captures the mcp-session-id header
```

## Verification

- `pytest tests/test_mcp.py -q` — 4 tests exercising the full loop over Streamable HTTP against the ASGI app.
