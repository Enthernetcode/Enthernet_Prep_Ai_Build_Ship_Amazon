# Submission status — Build, Ship, Shape: Amazon Developer Hackathon

**Primary track:** Alexa+
**Mini-challenges we qualify for:** AWS Builder, Open Source
**Deadline:** 2026-10-23 20:00 GMT+1
**Live URL:** https://eprep.enthernetservice.com

---

## 1. Is the site complete?

**Yes — for the §71 competition-critical demo path.** Technical implementation is done, deployed, and verified end-to-end.

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

- [ ] Flip `LLM_PROVIDER=openai` and wire the Examiner to rewrite questions through the LLM — so judges hear more natural phrasing
- [ ] Enable `ALEXA_VERIFY_SIGNATURE=true` once Amazon's cert chain is reachable
- [ ] Record a second take with a real Echo device if we obtain Alexa+ preview access

---

## 2. LLM: live or still mock after MCP is linked?

**Still mock — provider setting is wired but no tool calls out yet.**

**Why:** The 7 `prep.*` tools do their work with deterministic Python — heuristic question templates (Examiner), lexical-overlap scoring (Evaluator), running EMA (Weakness Agent), rule-based planner (Adaptive). None of them call `provider.generate()`. The provider abstraction is in place and *ready* — flipping `LLM_PROVIDER=openai` loads the OpenAI client correctly, but the tool code path never asks it to generate anything.

**Proof visible to a judge:** on the lab server, call the diagnostic:

```bash
curl -X POST https://eprep.enthernetservice.com/api/v1/mcp-lab/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'X-LLM-Provider: openai' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"prep.debug.resolve_provider","arguments":{}}}'
```

That tool reports the resolver chose `openai` — it just doesn't **call** OpenAI. Same deal for `bedrock`.

**To make the LLM demonstrably live** (post-submission wiring, ~30 min):

1. In `app/mcp/lab.py` (lab server only, judged stays untouched), wrap `prep.next_question` so that *when the resolver returns `openai` or `bedrock`* it passes the template question through `provider.generate(...)` with a short system prompt like "rewrite this interview question in a more natural voice".
2. Add 1 unit test with a mocked SDK verifying the LLM is actually called.
3. Deploy, record a before/after clip.

**Why I haven't done it yet:** The judged submission must not change behavior under judges. The lab is where that experiment lives. Say the word and I'll ship it — but it's a *nice-to-have*, not a submission requirement.

---

## 3. How to link MCP

Both endpoints are **live, Streamable HTTP, MCP spec 2025-11-25**, requiring `Authorization: Bearer <JWT>`:

| Role | URL |
|---|---|
| **Judged** — Alexa+ submission surface, frozen tool set | `https://eprep.enthernetservice.com/api/v1/mcp/` |
| **Lab** — same tools + `prep.debug.resolve_provider`; honors `X-LLM-Provider` | `https://eprep.enthernetservice.com/api/v1/mcp-lab/` |

### For judges — zero-friction token flow

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

### Claude Desktop config

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows:

```json
{
  "mcpServers": {
    "enthernet-prep-ai": {
      "type": "streamable-http",
      "url": "https://eprep.enthernetservice.com/api/v1/mcp/",
      "headers": {
        "Authorization": "Bearer <paste JWT from /demo/seed here>"
      }
    },
    "enthernet-prep-ai-lab": {
      "type": "streamable-http",
      "url": "https://eprep.enthernetservice.com/api/v1/mcp-lab/",
      "headers": {
        "Authorization": "Bearer <same JWT>",
        "X-LLM-Provider": "mock"
      }
    }
  }
}
```

Restart Claude Desktop. The judged entry shows 7 `prep.*` tools; the lab entry shows 8. Ask Claude: *"List my preparation projects. Start a mock interview on the first one."*

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

### Judging criteria — self-assessment

| Criterion | Where we land |
|---|---|
| **Tech Implementation** — well-built, effective use of required tech | Strong — 102 tests, deterministic + provider-abstracted, dual-MCP architecture isolates the judged submission from experimentation. |
| **Design** — complete, coherent product; intuitive interaction | Strong — polished landing (hero backdrop + step-by-step), admin dashboard, mic input, final-boss report. |
| **Potential Impact** — credible customer need beyond the hackathon | Strong — "readiness with proof" is a clear value prop; the engine serves interview, pitch, and exam prep off the same pipeline. |
| **Quality of the Idea** — creative use of the required tools | Strong — MCP-first voice architecture; one engine serves web + Alexa+; agentic flow is grounded rather than hallucinated. |

### Optional bonus — friction log

> Submissions with friction logs can earn up to a 10% judging bonus.

✅ `docs/friction-log.md` has 5 entries covering the Alexa+ console pivot, ASK sidetrack, MCP SDK migration, Bedrock model-id quirks, and S3/MinIO. One entry is flagged **Critical** (Alexa+ Developer Console closed to third parties).

Paste it verbatim into the Devpost "Product feedback" section.

---

## 5. Recommended next steps, in order

1. **Push to GitHub.** `git push` the pending commits (lab MCP + admin + mail + reset-password + git cleanup). If no public repo exists yet, create one and `git remote add origin ...`. Required for both the primary track's "GitHub code repository" rule and the Open Source mini-challenge.
2. **Register the admin account.** Open https://eprep.enthernetservice.com/register with `renuelroberts01@gmail.com`. Nav will then show an **Admin** link.
3. **Fill SMTP** (optional but recommended — needed for the password-reset flow to actually send email during judging).
4. **Record the demo video.** The 2:30 script in prior conversation turns targets the current UI (background-png hero → mic answer → MCP terminal split → final boss). Upload to YouTube public, grab the URL.
5. **Fill the Devpost form.** Project description, GitHub URL, demo video URL, track selections (Alexa+ + AWS Builder + Open Source), friction log, feature requests (optional).

If you want help with any of these — say which one.

---

*Generated 2026-09-24. Last verified live: all surfaces responding, 7-tool judged MCP + 8-tool lab MCP, 5/5 containers healthy on `89.47.249.196` under compose project `eprep`.*
