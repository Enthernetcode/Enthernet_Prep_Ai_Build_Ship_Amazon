# MCP integration (Alexa+ track)

Enthernet Prep AI exposes its preparation engine as a **self-hosted MCP server**. The primary submission surface for the Alexa+ track.

- **Transport:** Streamable HTTP (MCP spec **2025-11-25**)
- **Auth:** `Authorization: Bearer <jwt>` (same JWT the web app uses; obtain via `POST /api/v1/auth/login` or `POST /api/v1/demo/seed`)
- **Session mode:** `stateless_http=True` so any MCP client can hit us without session persistence concerns.

## Two endpoints

| Endpoint | Role | Tool count |
|---|---|---|
| `POST /api/v1/mcp/` | **Judged** — the submission surface. Frozen contract. | 7 `prep.*` tools |
| `POST /api/v1/mcp-lab/` | **Lab** — same 7 tools + a diagnostic. Honours `X-LLM-Provider` header for per-request provider override. | 8 (7 + `prep.debug.resolve_provider`) |

Both mounts share the same ASGI backend. The lab tools delegate directly to the judged implementations, so the behaviour is identical by construction. The only differences are the diagnostic tool and the resolver that lets the lab pick a different LLM provider per request.

## Tools

| Tool | What it does |
|---|---|
| `prep.list_projects` | Return the user's preparation projects. |
| `prep.extract_competencies` | Run the Knowledge Extraction Agent over uploaded chunks + refresh baseline readiness. |
| `prep.get_readiness` | Latest deterministic readiness snapshot (7 dimensions + overall). |
| `prep.start_session` | Begin a `mock_interview` or `final_boss` session. |
| `prep.next_question` | Ask the Examiner for the next grounded question. Idempotent within a turn. Response includes `question_source` (`"template"` or the active LLM provider name). |
| `prep.submit_answer` | Evaluate an answer, upsert weakness records, run the adaptive planner, recompute readiness. When an LLM provider is active, response gains a `rationale` field; `rationale_source` identifies the provider or `"none"`. |
| `prep.finish_session` | Mark the session complete and return the final readiness report. |
| `prep.debug.resolve_provider` *(lab only)* | Returns the LLM + embedding provider the lab resolver picked for this request and the source of the decision (`header` / `db` / `settings`). |

Every tool wraps the same engine the REST API uses (`app/api/v1/sessions.py` + the agents). No duplicated business logic. Changing the engine changes both surfaces at once.

## Three ways to test it

### Path A: Built-in browser MCP tester (zero external software)

The frontend ships a page that *is* an MCP client at `/mcp-tester`. It handles the full Streamable HTTP flow (initialize → initialized notification → tools/list → tools/call) from the browser. Just press the four numbered buttons:

1. **Mint a demo token** → `POST /api/v1/demo/seed` (no login required).
2. **Initialize MCP session** → handshake, server identifies as `enthernet-prep-ai`.
3. **List tools** → renders a card per tool with a form derived from `inputSchema`.
4. **Invoke a tool** → shows structured response + raw wire log.

Endpoint toggle at the top switches between judged and lab. On lab, an `X-LLM-Provider` dropdown lets you override the resolver per call.

This is the simulated-experience path called out in the hackathon FAQ.

### Path B: `curl`

```bash
# 1. Demo token (no login required):
TOKEN=$(curl -sS -X POST http://localhost:8000/api/v1/demo/seed \
  -H 'Content-Type: application/json' -d '{}' | jq -r .access_token)

# 2. Initialize MCP session (captures mcp-session-id if the server sends one):
curl -sS -X POST http://localhost:8000/api/v1/mcp/ -D /tmp/hdr \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{
           "protocolVersion":"2025-11-25","capabilities":{},
           "clientInfo":{"name":"curl","version":"1"}}}'
SID=$(grep -i '^mcp-session-id' /tmp/hdr | awk '{print $2}' | tr -d '\r')

# 3. Mandatory initialized notification:
curl -sS -X POST http://localhost:8000/api/v1/mcp/ \
     -H "Authorization: Bearer $TOKEN" \
     -H "mcp-session-id: $SID" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'

# 4. List tools:
curl -sS -X POST http://localhost:8000/api/v1/mcp/ \
     -H "Authorization: Bearer $TOKEN" \
     -H "mcp-session-id: $SID" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Path C: Any Streamable HTTP MCP client

Point any MCP client that implements the Streamable HTTP spec (2025-11-25) at the endpoint URL with the Bearer header. Example minimal config shape:

```json
{
  "type": "streamable-http",
  "url": "http://localhost:8000/api/v1/mcp/",
  "headers": {
    "Authorization": "Bearer <JWT from /api/v1/demo/seed>"
  }
}
```

Nothing in the server is specific to any particular MCP client. The server speaks the protocol, the client wraps it.

## LLM wiring (optional enhancement)

When `LLM_PROVIDER=openai` or `LLM_PROVIDER=bedrock` is set on the server + the matching credentials are configured:

- `prep.next_question` passes the templated question through the LLM for natural rephrasing. The response's `question_source` field flips from `"template"` to the provider name.
- `prep.submit_answer` attaches a 1–2 sentence coach `rationale` to the evaluation response. Deterministic rubric scores are unchanged.

Silent-fallback. If the provider errors (quota, network, auth), the deterministic path is used and the tool call never fails. 108 tests cover both the deterministic defaults and the LLM paths (via mocked provider SDKs. No live API cost).

The lab endpoint honours an `X-LLM-Provider` header per request, so callers can A/B providers without touching server config:

```bash
curl -X POST http://localhost:8000/api/v1/mcp-lab/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-LLM-Provider: openai" \
  ...
```

## Verification

- `pytest tests/test_mcp.py -q`: 4 tests exercising the judged mount end-to-end.
- `pytest tests/test_mcp_lab.py -q`: 4 tests covering the lab mount, provider resolver, and header override.
- `pytest tests/test_llm_wired_agents.py -q`: 6 tests covering the LLM paths for Examiner + Evaluator.

Full suite: **108 passing** on a clean prod image build.
