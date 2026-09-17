# Alexa+ Integration

Authoritative source: `AGENT.md` §31–33.

## Principle

Alexa+ is an **adapter** on top of `/api/v1`. The same preparation engine serves web, Alexa+, and future interfaces. No preparation business logic lives inside Alexa handlers.

```
Alexa+ event  ──▶  Amazon integration adapter  ──▶  /api/v1/sessions  ──▶  Agent runtime
```

## Wired endpoint

`POST /api/v1/alexa` — accepts the standard Alexa request envelope. Reuses `Examiner → Evaluator → Weakness → Adaptive → Readiness` (see `app/api/v1/sessions.py`) so voice and web share one loop.

### Intent → behaviour

| Intent | Behaviour |
|---|---|
| `LaunchRequest` | Enumerates the user's latest projects and prompts for a mode. |
| `StartInterviewIntent` | Creates a `mock_interview` session on the most recent project and speaks the first question. |
| `FinalBossIntent` | Creates a `final_boss` session (difficulty 5, hints off, longer cap). |
| `AnswerIntent` (slot `answer`) | Runs the answer through the full loop, speaks the updated readiness + next question. |
| `AMAZON.HelpIntent` | Reminds the user of the two entry commands. |
| `AMAZON.StopIntent` / `AMAZON.CancelIntent` | Ends the session politely. |
| `SessionEndedRequest` | No-op, closes session. |

### Account linking (§32)

Alexa passes the linked user's OAuth access token in `session.user.accessToken`. The Amazon-side skill configuration must forward it as `Authorization: Bearer <token>` to this endpoint. Our JWT check in `get_current_user` is reused verbatim — no spoken-name identification.

For the demo we assume the same JWT the web app issues; a production wiring should issue Amazon-scoped tokens via Login-with-Amazon.

## Not implemented (must land before Amazon submission)

1. **Request signature verification.** The current handler trusts the caller. Alexa cert requires validating the `Signature`, `SignatureCertChainUrl`, and the request-body timestamp window (150 s).
2. **Skill package** (interaction model JSON + endpoint URL). Placeholder env vars: `ALEXA_SKILL_ID`, `ALEXA_CLIENT_ID`, `ALEXA_CLIENT_SECRET`.
3. **Latency guard.** Alexa gives ~8 s per turn. Evaluator + planner are synchronous — fine with the mock provider, but the OpenAI path should be moved to a progressive-response pattern.

## Example envelope (for `curl` smoke test)

```json
{
  "version": "1.0",
  "session": {"attributes": {}, "user": {"accessToken": "<JWT>"}},
  "context": {},
  "request": {
    "type": "IntentRequest",
    "intent": {"name": "StartInterviewIntent"}
  }
}
```
