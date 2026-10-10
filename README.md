# Enthernet Prep AI

**Live in the Moment.**

Agentic AI readiness engine — turns user-uploaded material (CVs, JDs, pitch decks, notes) into a personal competency map, drills you with grounded adaptive questions, and tracks a deterministic readiness score that moves as you improve.

Submission for the **Build, Ship, Shape: Amazon Developer Hackathon**, Alexa+ track.

- Primary submission surface — **MCP server** at `POST /api/v1/mcp/` (Streamable HTTP, spec **2025-11-25**)
- Companion web app at `/` (Next.js) + classic Alexa webhook at `/api/v1/alexa` (fallback demo surface)
- 108 tests passing, Apache-2.0

---

## Quickstart (what judges run)

Prereqs: Docker + Docker Compose. No API keys required — defaults use a deterministic mock provider so the full MCP exchange works offline.

```bash
git clone https://github.com/Enthernetcode/Eprep.git
cd Eprep
cp .env.example .env
docker compose up --build
```

The `backend` container runs `alembic upgrade head` automatically on start, so there's no "set up the database" step.

Once containers are healthy:

| What | Where |
|---|---|
| **MCP server (Alexa+ submission surface)** | `POST http://localhost:8000/api/v1/mcp/` |
| MCP lab (same tools + provider-override header) | `POST http://localhost:8000/api/v1/mcp-lab/` |
| REST API base | `http://localhost:8000/api/v1` |
| Web app | `http://localhost:3000` |
| API docs | `http://localhost:8000/docs` |
| MinIO console | `http://localhost:9001` (user/pass from `.env`) |

Run the backend test suite (108 tests, ~40 s):

```bash
docker compose exec backend pytest -q
```

---

## Testing the MCP server (the Alexa+ story)

Per the Devpost rules, judges act as the MCP client. **Three paths — pick whichever is easiest for you.**

### Path A — Built-in browser MCP tester (recommended, zero external software)

Open `http://localhost:3000/mcp-tester` after `docker compose up`. It's a page that *is* an MCP client — it sends `initialize`, `notifications/initialized`, `tools/list`, and `tools/call` requests directly from the browser to the server. Just press the four buttons in order:

1. **Mint a demo token** — calls `POST /api/v1/demo/seed`, no login required.
2. **Initialize MCP session** — does the handshake, captures `mcp-session-id`.
3. **List tools** — pulls the 7 (or 8, on lab) `prep.*` tool manifests.
4. **Invoke a tool** — click any tool card, fill its arguments, see the structured response + raw wire log.

Toggle between the judged (`/api/v1/mcp/`) and lab (`/api/v1/mcp-lab/`) mounts in the top-left. On lab you can also set the `X-LLM-Provider` override header per call.

### Path B — curl

### Zero-friction token (no login required)

```bash
TOKEN=$(curl -sS -X POST http://localhost:8000/api/v1/demo/seed \
  -H 'Content-Type: application/json' -d '{}' | jq -r .access_token)
```

That one call creates a demo user, uploads a realistic CV + job description, extracts 57 competencies, and computes a baseline readiness score — so the next `prep.*` tool call returns rich data, not empty state.

### MCP tool list

```bash
# Initialize session (captures mcp-session-id)
curl -sS -X POST http://localhost:8000/api/v1/mcp/ -D /tmp/mcphdr \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{
       "protocolVersion":"2025-11-25","capabilities":{},
       "clientInfo":{"name":"curl","version":"1"}}}'

SID=$(grep -i '^mcp-session-id' /tmp/mcphdr | awk '{print $2}' | tr -d '\r')

# Mandatory initialized notification
curl -sS -X POST http://localhost:8000/api/v1/mcp/ \
  -H "Authorization: Bearer $TOKEN" -H "mcp-session-id: $SID" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'

# List tools
curl -sS -X POST http://localhost:8000/api/v1/mcp/ \
  -H "Authorization: Bearer $TOKEN" -H "mcp-session-id: $SID" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Expected 7 tools, prefixed `prep.`:

| Tool | Purpose |
|---|---|
| `prep.list_projects` | User's preparation projects |
| `prep.extract_competencies` | Build the competency map from uploaded docs + refresh baseline readiness |
| `prep.get_readiness` | Latest 7-dim readiness snapshot |
| `prep.start_session` | Begin `mock_interview` or `final_boss` |
| `prep.next_question` | Grounded question from the Examiner (idempotent per turn) |
| `prep.submit_answer` | Multi-dim evaluation + adaptive planner + readiness recompute |
| `prep.finish_session` | Final readiness report |

Lab endpoint adds an 8th tool, `prep.debug.resolve_provider`, and honours an `X-LLM-Provider: mock|openai|bedrock` header so the LLM provider can be swapped per-request.

### Path C — Any MCP client (Claude Desktop, custom scripts, etc.)

Claude Desktop example `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "enthernet-prep-ai": {
      "type": "streamable-http",
      "url": "http://localhost:8000/api/v1/mcp/",
      "headers": { "Authorization": "Bearer <paste JWT from /demo/seed>" }
    }
  }
}
```

Restart Claude Desktop — 7 `prep.*` tools appear. Ask: *"list my preparation projects, then start a mock interview on the first one."*

Any client that implements the MCP Streamable HTTP spec (2025-11-25) works equivalently. Nothing in the server is Claude-specific.

---

## Architecture

```
backend/       FastAPI + MCP (judged + lab) + agents + REST API
  app/mcp/     Both MCP servers — server.py (judged) + lab.py (per-request provider resolver)
  app/agents/  Document, Knowledge Extraction, Examiner, Evaluator, Weakness, Adaptive Planner, Coach
  app/providers/ Provider abstraction — mock (default, deterministic) + openai + bedrock
frontend/      Next.js 15 App Router — landing, admin dashboard, session UI with mic + TTS
db/            Postgres init scripts (pgvector)
docs/          architecture, mcp-integration, alexa-integration, friction-log, cheatsheet
```

The agents are deterministic by default so the demo works offline with zero API keys. When `LLM_PROVIDER=openai` + `OPENAI_API_KEY` are set, the Examiner's question-phrasing and Evaluator's rationale pass through the LLM — fail-silent fallback keeps everything working if the key is missing or the provider errors.

More detail in [`docs/mcp-integration.md`](./docs/mcp-integration.md) and [`SUBMISSION.md`](./SUBMISSION.md).

---

## Mini-challenges

- **AWS Builder** — `backend/app/providers/bedrock.py` implements `BedrockLLMProvider` + `BedrockEmbeddingProvider` via `bedrock-runtime.converse` and `invoke_model`. Switch with `LLM_PROVIDER=bedrock` + AWS creds. Covered by 4 tests.
- **Open Source** — this repo, Apache-2.0, public on GitHub.

Friction log for the "Product feedback" bonus (up to +10% judging): [`docs/friction-log.md`](./docs/friction-log.md).

---

## License

[Apache-2.0](./LICENSE).

Built by [Enthernet](https://enthernetservice.com/).
