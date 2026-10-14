# Submission status: Build, Ship, Shape: Amazon Developer Hackathon

**Primary track:** Alexa+
**Mini-challenges we qualify for:** AWS Builder, Open Source
**Deadline:** 2026-10-23 20:00 GMT+1
**Live URL:** https://eprep.enthernetservice.com

---

## 1. Is the site complete?

**Yes, for the §71 competition-critical demo path.** Technical implementation is done, deployed, and verified end-to-end.

| Area | State |
|---|---|
| Backend — 102 tests passing | ✅ Lab + Judged MCP, admin dashboard, SMTP, announcements, password reset |
| Frontend | ✅ Hero backdrop, step-by-step, admin hub, mic input, final-boss report |
| Deploy | ✅ TLS cert valid through 2026-12-17; migrations at `d4a1b2c3e004 (head)` |
| Alexa signature verification | ✅ Implemented + 11 tests; off by default for the demo |

**Blocking formal submission** (not strictly "complete" until done):

- [ ] Push the latest code to GitHub (`git push`)
- [ ] Record the demo video (<3 minutes, YouTube or Vimeo, public)
- [ ] Register `renuelroberts01@gmail.com` on the live site so the admin UI lights up
- [ ] Configure SMTP via **Admin → SMTP** tab so password reset actually sends email
- [ ] Fill out the Devpost submission form

**Nice-to-haves that would strengthen the submission:**

- [ ] Set `OPENAI_API_KEY` (or Bedrock creds) on the VPS `.env` if we want our hosted instance to serve LLM-rephrased questions. Opt-in enhancement; the submission does not require it.
- [ ] Enable `ALEXA_VERIFY_SIGNATURE=true` once Amazon's cert chain is reachable
- [ ] Record a second take with a real Echo device if we obtain Alexa+ preview access

---

## 2. How the LLM fits in (and who's calling what)

Per the Alexa+ track rules and the Devpost FAQ, **the judge is the MCP client**. They connect to our MCP server via the built-in browser tester, a bespoke MCP page, or `git clone` + their own tooling. The *judge-side* client (an Alexa+ simulator, our `/mcp-tester` web page, or any Streamable HTTP MCP client) decides when to call which tool. Our server returns structured tool results. That is the Alexa+ integration.

**Our server-side LLM is an *enhancement*, not the integration.** When our server is configured with an `OPENAI_API_KEY` (or Bedrock creds) and `LLM_PROVIDER` set to that provider:

- **Examiner** (`prep.next_question`) still picks the competency + difficulty deterministically, then asks the LLM to rewrite the templated question in natural interviewer prose. Response carries `question_source = template | openai | bedrock`.
- **Evaluator** (`prep.submit_answer`) still scores all seven rubric dimensions deterministically (so scores stay comparable across answers and tests stay stable), then attaches a 1–2 sentence `rationale` field written by the LLM. Response carries `rationale_source = none | openai | bedrock`.

Everything else (adaptive planner, weakness map, readiness recompute, grounding) stays deterministic.

**Silent-fallback.** If the LLM errors (quota, network, auth), the tool quietly falls back: `question_source` becomes `template`, `rationale` is omitted. The judge's MCP call never fails.

**Default stance.** `LLM_PROVIDER=mock` is the default so judges who `git clone` + `docker compose up` get a working MCP exchange without any API key. Setting the key later is additive; the deterministic scores don't change, only the human-readable text wrapping them.

**On the lab server** judges can override per request:

```bash
curl -X POST https://eprep.enthernetservice.com/api/v1/mcp-lab/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'X-LLM-Provider: openai' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"prep.next_question","arguments":{"session_id":"..."}}}'
```

If our server has an OpenAI key, that call returns an LLM-rephrased question. Without a key, it transparently falls back to the template. The MCP contract judges rely on is unchanged either way.

**Verified by 6 new tests** in `backend/tests/test_llm_wired_agents.py` covering both success paths and silent fallback with a `FakeLLM` provider (no live API cost).

---

## 3. How to link MCP

**The fastest path. A browser tab, no external software:** open `http://localhost:3000/mcp-tester` (or `https://eprep.enthernetservice.com/mcp-tester` on the hosted instance). The page *is* an MCP client. It issues `initialize`, `notifications/initialized`, `tools/list`, and `tools/call` directly from the browser to the server. Press the four numbered buttons in order; each `prep.*` tool shows up as a card with its own input form and response panel. This is the simulated-experience path called out in the Devpost Alexa+ FAQ.

Below are the equivalent paths for judges who prefer curl or an existing MCP client.


Both endpoints are **live, Streamable HTTP, MCP spec 2025-11-25**, requiring `Authorization: Bearer <JWT>`:

| Role | URL |
|---|---|
| **Judged** — Alexa+ submission surface, frozen tool set | `https://eprep.enthernetservice.com/api/v1/mcp/` |
| **Lab** — same tools + `prep.debug.resolve_provider`; honors `X-LLM-Provider` | `https://eprep.enthernetservice.com/api/v1/mcp-lab/` |

### For judges: demo token flow

`/api/v1/demo/seed` is public and no-login-required. One curl mints a token + seeds a realistic project with 57 competencies and a baseline readiness score:

```bash
TOKEN=$(curl -sS -X POST https://eprep.enthernetservice.com/api/v1/demo/seed \
  -H 'Content-Type: application/json' -d '{}' | jq -r .access_token)

# List tools:
curl -sS -X POST https://eprep.enthernetservice.com/api/v1/mcp/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Any Streamable HTTP MCP client

Minimal config shape most MCP clients accept:

```json
{
  "type": "streamable-http",
  "url": "https://eprep.enthernetservice.com/api/v1/mcp/",
  "headers": {
    "Authorization": "Bearer <paste JWT from /demo/seed here>"
  }
}
```

Judged entry exposes 7 `prep.*` tools once initialized. The lab endpoint at `/api/v1/mcp-lab/` exposes 8 (7 + `prep.debug.resolve_provider`) and additionally honours an `X-LLM-Provider: mock|openai|bedrock` header for per-call provider override.

### Tool inventory

| Tool | What it does |
|---|---|
| `prep.list_projects` | User's preparation projects |
| `prep.extract_competencies` | Build the competency map from uploaded docs + refresh baseline readiness |
| `prep.get_readiness` | Latest 7-dim readiness snapshot |
| `prep.start_session` | Begin `mock_interview` or `final_boss` session |
| `prep.next_question` | Grounded question from the Examiner (idempotent per turn) |
| `prep.submit_answer` | Evaluate, update weakness map, run adaptive planner, recompute readiness |
| `prep.finish_session` | Mark complete + final readiness report |
| `prep.debug.resolve_provider` *(lab only)* | Shows which provider + model the lab resolver picked, and the source (header / db / settings) |

---

## 4. Devpost alignment

Checked against the rules on the hackathon page.

### Primary submission requirements (Alexa+)

| Requirement | Status |
|---|---|
| Self-hosted MCP server, spec 2025-11-25+, Streamable HTTP | ✅ Both `/api/v1/mcp/` and `/api/v1/mcp-lab/` |
| Repo actually calls MCP in code (not just README) | ✅ `app/mcp/server.py`, `app/mcp/lab.py`, mounted in `app/main.py`, 12 MCP-specific tests |
| GitHub repo — public with OSS license OR private shared with `testing@devpost.com` + `@AmazonAppDev` | 🟡 Apache-2.0 LICENSE in place; latest code not yet pushed |
| Demo video <3 min, YouTube/Vimeo, public, English | ❌ To record |
| MCP server shown in action in video | ❌ Depends on recording |
| Text description of the project | ❌ Needs to be written in the Devpost form |
| Product feedback for every Amazon tool / API / SDK used | ✅ `docs/friction-log.md` has 5 entries |
| Pick track(s) and mini-challenge(s) | ❌ Pick in Devpost form (Alexa+ + AWS Builder + Open Source) |

### Mini-challenges

| Challenge | Prize | Status |
|---|---|---|
| **AWS Builder** — use AWS services with documented integration | $5K cash + $5K AWS credits | ✅ `app/providers/bedrock.py` (LLM + embeddings via Converse / invoke_model), 4 tests. Document in Devpost form's AWS feedback section. |
| **Open Source** — ship a new OSS project with license, or a public PR, during the hackathon window | $5K cash + $5K AWS credits | 🟡 Apache-2.0 LICENSE at root; repo needs to be pushed public on GitHub inside the window to count. Include the repo URL + a short description of what you built, how it works, and why it matters, per the rules. |

### Judging criteria: self-assessment

| Criterion | Where we land |
|---|---|
| **Tech Implementation** — well-built, effective use of required tech | Strong — 102 tests, deterministic + provider-abstracted, dual-MCP architecture isolates the judged submission from experimentation. |
| **Design** — complete, coherent product; intuitive interaction | Strong — polished landing (hero backdrop + step-by-step), admin dashboard, mic input, final-boss report. |
| **Potential Impact** — credible customer need beyond the hackathon | Strong — "readiness with proof" is a clear value prop; the engine serves interview, pitch, and exam prep off the same pipeline. |
| **Quality of the Idea** — creative use of the required tools | Strong — MCP-first voice architecture; one engine serves web + Alexa+; agentic flow is grounded rather than hallucinated. |

### Optional bonus: friction log

> Submissions with friction logs can earn up to a 10% judging bonus.

✅ `docs/friction-log.md` has 5 entries covering the Alexa+ console pivot, ASK sidetrack, MCP SDK migration, Bedrock model-id quirks, and S3/MinIO. One entry is flagged **Critical** (Alexa+ Developer Console closed to third parties).

Paste it verbatim into the Devpost "Product feedback" section.

---

## 5. Recommended next steps, in order

1. **Push to GitHub.** `git push` the pending commits (lab MCP + admin + mail + reset-password + git cleanup). If no public repo exists yet, create one and `git remote add origin ...`. Required for both the primary track's "GitHub code repository" rule and the Open Source mini-challenge.
2. **Register the admin account.** Open https://eprep.enthernetservice.com/register with `renuelroberts01@gmail.com`. Nav will then show an **Admin** link.
3. **Fill SMTP** (optional but recommended. needed for the password-reset flow to actually send email during judging).
4. **Record the demo video.** The 2:30 script in prior conversation turns targets the current UI (background-png hero → mic answer → MCP terminal split → final boss). Upload to YouTube public, grab the URL.
5. **Fill the Devpost form.** Project description, GitHub URL, demo video URL, track selections (Alexa+ + AWS Builder + Open Source), friction log, feature requests (optional).

If you want help with any of these. Say which one.

---

*Generated 2026-09-24. Last verified live: all surfaces responding, 7-tool judged MCP + 8-tool lab MCP, 5/5 containers healthy on `89.47.249.196` under compose project `eprep`.*
