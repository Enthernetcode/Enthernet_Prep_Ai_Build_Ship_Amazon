# Devpost submission draft: Enthernet Prep AI

Copy each section below into the matching Devpost form field. Markdown is supported in the long description.

---

## Project name

**Enthernet Prep AI**

## Elevator pitch (tagline, keep short: Devpost caps this at ~200 chars)

> Live in the Moment. An agentic MCP server that turns your CV, JD, or pitch into a competency map, drills you with grounded adaptive questions, and tracks readiness that moves as you improve. Alexa+-ready, voice-native, 108 tests.

## Tracks & mini-challenges entering

- **Primary track:** Alexa+
- **Mini-challenges:** AWS Builder · Open Source

---

## The long description (paste into the main project description box)

> *Markdown below. If Devpost strips headings, keep the bold labels and horizontal rules.*

### Inspiration

Interview prep tools fall into two camps: static question banks that don't know who you are, and chatbots that will cheerfully invent "feedback" with zero grounding in what you actually said. Neither tells you whether you're ready. They just tell you whether you *feel* ready.

The Alexa+ track asked for an MCP server that an agentic voice assistant could plug into. That's a chance to build the preparation tool we actually want: one engine behind the voice, grounded in your real material, with a readiness number you can defend to a hiring manager. Or a VC. Before you walk into the room.

### What it does

**Enthernet Prep AI is an agentic readiness engine** served as a Model Context Protocol server (spec 2025-11-25, Streamable HTTP). A conversational Alexa+ client (or any Streamable HTTP MCP client, or our browser-only MCP tester) drives the user through:

1. **Bring your material**: upload CV, JD, pitch deck, notes.
2. **See your competency map**: the Knowledge Extraction Agent pulls skills, technologies, metrics, and claims from every chunk; the result is the vocabulary everything else drills against.
3. **Set a baseline readiness**: deterministic, modest by design, because readiness is proven through performance, not implied by documents.
4. **Practice in adaptive simulations**: the Examiner Agent generates a grounded question tied to a specific competency; the Evaluator Agent scores the answer across 7 independent rubric dimensions (accuracy, completeness, relevance, conciseness, evidence, communication, response time); the Adaptive Planner decides whether to level up, follow up, probe deeper, or call the Coach.
5. **Face the Final Boss**: graded assessment, hints off, produces a readiness report you can act on.

Every tool call returns structured data the Alexa+ client narrates to the user. Scores are deterministic (so they're reproducible and judge-testable). When an OpenAI or Bedrock key is set on the server, the Examiner's question-phrasing and Evaluator's rationale pass through the LLM for warmer natural language. Silent fallback keeps everything working if the key is missing or the provider errors.

### How we built it

- **MCP server**: Python 3.12, FastAPI, [`mcp`](https://pypi.org/project/mcp/) SDK v2.2, Streamable HTTP transport. Two mounts:
  - `/api/v1/mcp/`: the frozen submission surface with 7 `prep.*` tools.
  - `/api/v1/mcp-lab/` — mirrors the 7 tools + a `prep.debug.resolve_provider` diagnostic. Honours an `X-LLM-Provider: mock|openai|bedrock` header so we can A/B providers per request without touching the submission mount.
- **Agents**: one Python module per `Agent.md`-defined role (Document, Knowledge Extraction, Examiner, Evaluator, Weakness, Adaptive Planner, Coach). All deterministic by default so the demo works offline with zero API keys.
- **Provider abstraction**: `MockLLMProvider` (deterministic SHA-seeded vectors + canned text, for tests and offline demos), `OpenAILLMProvider`, `BedrockLLMProvider` (Converse API + invoke_model). Pluggable via config.
- **Persistence**: Postgres 16 with pgvector for chunk embeddings; MinIO for uploads; Redis available for background queues.
- **Readiness engine**: pure Python, deterministic. §27 of our internal spec; same inputs always produce the same seven-dimension snapshot.
- **Frontend**: Next.js 15 App Router. Landing, admin dashboard (providers + SMTP + announcements), interview session UI with mic input + optional TTS, final-boss report, and **a built-in browser MCP client at `/mcp-tester`** that satisfies the "web page that acts as an actual MCP client" path called out in the Devpost Alexa+ FAQ.
- **Infra**: Docker Compose for local, Ubuntu VPS + nginx + Let's Encrypt + a `docker-compose.override.yml` for the hosted instance. `alembic upgrade head` runs automatically on backend startup so judges never do manual DB setup.
- **Tests**: 108 passing on a clean prod image, covering every agent, every MCP tool, every admin endpoint, the password-reset flow, the Alexa signature verifier, and the OpenAI + Bedrock provider wrappers (both mocked).

### Challenges we ran into

- **Alexa+ Developer Console is gated to select partners.** We can't register our MCP server as a real Alexa+ Agent Skill. the console shows "coming soon" to the general developer account. We built against the sanctioned fallback (self-hosted MCP + simulated-experience web client) per the Alexa+ FAQ. See `docs/friction-log.md`.
- **The MCP Python SDK migrated between v1 and v2** mid-project. rename of `FastMCP` → `MCPServer`, `McpError` → `MCPError`, split of exception types. Our pin to `mcp>=2.2` and ad-hoc refactor dealt with it, but the SDK's own examples still show v1 shapes.
- **ASGI lifespan under `httpx.ASGITransport`** doesn't fire by default. The MCP SDK's `session_manager.run()` needs the lifespan hooks, so tests crashed on startup. Added `asgi-lifespan` as a dev dep and wrapped it around the test client.
- **Shipping a browser MCP client that works stateless.** Our server mounts both MCP endpoints as `stateless_http=True` so judges can hit them from anywhere without session persistence. which means `initialize` doesn't return an `mcp-session-id` header. We caught (via our own end-to-end audit of the tester page) a UI gating bug that would have made step 3 permanently disabled after a successful handshake. Fixed by gating on an `initialized: boolean` flag instead.

### Accomplishments that we're proud of

- **A simple path for judges.** Open `http://localhost:3000/mcp-tester` after `docker compose up`, press four buttons, see every `prep.*` tool execute and return structured data. No external MCP client, no curl, no SDK, no API keys.
- **The judged mount is byte-identical to the day we froze it.** The admin dashboard, LLM wiring, lab server, and SMTP/announcements all live separately. Our 4 original `test_mcp.py` tests still pass unchanged.
- **Silent-fallback LLM path.** If a judge runs the repo with no OpenAI key, the Examiner falls back to a deterministic template and the Evaluator skips the LLM rationale. Nothing breaks. If a key *is* set, the same tools quietly produce warmer, more natural output. same contract, richer wrapper.
- **108 tests on a clean prod image build** including provider-side mocks for OpenAI + Bedrock so the LLM paths are proven without live API cost.

### What we learned

- MCP is a good match for an agentic education product because the server stays "the engine" and the client stays "the voice". no coupling to a specific LLM.
- Deterministic defaults are a feature, not a limitation. They make a hackathon demo reproducible, make tests trivial, and let an LLM be an opt-in enhancement rather than a dependency.
- Admin surfaces (SMTP config, provider override, announcements) that live separately from the submission surface are the right call. iteration risk doesn't leak into the judged path.

### What's next

- When Amazon opens Alexa+ Developer Console registrations beyond preview partners, register this exact MCP server URL. the server contract already matches.
- Wire the Vision Agent (§11) so photo-of-notes uploads join the pipeline.
- Add the Consensus Engine (§40): multiple Evaluator passes merged by a Critic. for the Final Boss mode.

---

## Try it out: URLs to list in Devpost's "Try it out" section

- **Live site**: <https://eprep.enthernetservice.com>
- **Browser-based MCP tester (judge's primary path)**: <https://eprep.enthernetservice.com/mcp-tester>
- **GitHub repo**: <https://github.com/Enthernetcode/Eprep>
- **MCP endpoint (direct)**: `POST https://eprep.enthernetservice.com/api/v1/mcp/`

Judges can also `git clone + docker compose up --build` and reach the same tester at `http://localhost:3000/mcp-tester`. Zero API keys required (mock provider is deterministic).

---

## "Built with" tags (Devpost tag field: pick as many as apply)

```
python, fastapi, sqlalchemy, postgresql, pgvector, redis, docker,
nextjs, react, typescript, tailwindcss, mcp, model-context-protocol,
anthropic, openai, aws, aws-bedrock, minio, alembic, pytest, nginx,
letsencrypt, apache-2
```

---

## Open Source mini-challenge: the extra required fields

- **Repo URL:** <https://github.com/Enthernetcode/Eprep>
- **Open-source license:** Apache-2.0 (file at repo root)
- **GitHub username:** `Enthernetcode` (plus contributor accounts as applicable)
- **Contribution URL** (same repo, main submission): <https://github.com/Enthernetcode/Eprep/commits/main>
- **Short description** (what / how / why):

  > A production-grade MCP server that implements the Alexa+ track's reference integration pattern end-to-end. Spec 2025-11-25 over Streamable HTTP, with 7 grounded preparation tools, dual mount so experimental changes never touch the submission surface, pluggable LLM providers (mock / OpenAI / Bedrock), browser-only MCP client, admin dashboard, and 108 tests. Apache-2.0, dependency-free start (`docker compose up` → working MCP exchange with zero API keys), judge-ready out of the box.
  >
  > *Why it matters:* the Alexa+ developer tooling (Agent Skills console, MCP Toolkit, Web Simulator) is still gated to select partners, so independent builders can't verify their work against first-party Alexa+ clients. This repo is a reference implementation + a browser MCP client that any developer. Not just Alexa+ preview partners. Can run and inspect.

---

## AWS Builder mini-challenge: paste into the AWS feedback section

**Services used:** Amazon Bedrock (Converse API for Anthropic Claude, Meta Llama, Amazon Titan, Mistral, and Cohere models; `invoke_model` for embeddings via Titan Embed v2 and Cohere Embed English).

**How we used it:** `backend/app/providers/bedrock.py` implements `BedrockLLMProvider` and `BedrockEmbeddingProvider` behind the same abstract interface as the mock and OpenAI providers. The MCP tools' optional LLM enhancement path hits Bedrock when `LLM_PROVIDER=bedrock` and AWS creds are set. No code changes required to swap providers.

**What worked well:** `converse` is model-agnostic. A single code path handles every family on Bedrock without per-provider branching. `inferenceConfig` is a clean spot for shared knobs (max tokens, temperature).

**What needs work:** Model-id inconsistency between embedding and inference endpoints. `converse` uses cross-region IDs like `us.anthropic.claude-3-5-sonnet-20241022-v2:0`; embeddings use bare IDs like `amazon.titan-embed-text-v2:0`. A `bedrock-runtime.resolve_model_id` helper, or a unified `embed()` action parallel to `converse()`, would remove a step. Request body shape for `invoke_model` also differs between Titan and Cohere families; we branch on the model-id prefix in our wrapper.

**Would we build with it again?** Yes. The provider abstraction cost about 80 lines of Python plus 4 mocked tests. Being able to flip between Bedrock and OpenAI with an env var matters in a hackathon when we don't know in advance which key the judge has.

Also used: Amazon S3 (via S3-compatible MinIO in dev. Zero-code switch to real S3 in prod). AWS SDK stability makes third-party S3 implementations like MinIO trivial.

---

## Product feedback (bonus: up to +10% judging)

Paste the five entries from `docs/friction-log.md` verbatim. Short summary of what they cover:

1. **Alexa+ Developer Console**. "coming soon" page for third-party developers, no visible preview-request affordance. We lost ~20 min discovering the Agent Skills path was gated before pivoting to the MCP-server path. *Severity: Important.* Suggestion: inline "Preview access required" affordance on the Alexa+ console tile.
2. **Alexa Skills Kit**: the classic ASK console doesn't flag that classic custom skills don't count for the Alexa+ track. One-line banner would have saved us ~30 min. *Severity: Nice-to-have.*
3. **MCP Python SDK v1 → v2 migration**: confusing because the SDK's own README examples still show v1 shapes. The migration-guide link in error messages is excellent though. *Severity: Nice-to-have.* Suggestion: add a "Mount under FastAPI" section to the official docs.
4. **Amazon Bedrock**: model-id inconsistency between `converse` and `invoke_model`; embedding body shape differs by provider family. *Severity: Nice-to-have.*
5. **MinIO / S3 compatibility**: kudos; third-party server stability depends on SDK stability.

Also includes feature requests (Alexa+ Add-on local emulator; unified Bedrock `embed()` action) and a 10% judging-bonus friction-log entry format.

---

## "If your project existed before the hackathon" explanation

The repository was created and the first commit landed inside the hackathon submission window. See `git log --reverse --oneline` on the main branch. Every line of code shipped during the window.

---

## Demo video: placeholder until recorded

**TODO:** record a <3 min walkthrough on YouTube or Vimeo, public. Suggested script (same recording plan sent in `SUBMISSION.md`):

- 0:00–0:15. Hook ("ready, with proof") against the landing hero
- 0:15–0:50. One-click demo seed → dashboard with 57 competencies + baseline 43%
- 0:50–1:30. Browser MCP tester: open /mcp-tester, press four buttons, show prep.* tools returning real data
- 1:30–2:10. Lab endpoint: toggle `X-LLM-Provider` header, show the resolver flip
- 2:10–2:40. Session UI with mic input → final-boss readiness report
- 2:40–2:50. Close, "Live in the Moment"

Once uploaded, paste the URL in Devpost's video field.
