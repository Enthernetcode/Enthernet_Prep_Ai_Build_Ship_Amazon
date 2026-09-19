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

## Request signature verification

Implemented in `app/alexa/verify.py` and gated by `ALEXA_VERIFY_SIGNATURE` (default `false` for dev/demo). When on:

- `SignatureCertChainUrl` header must be `https://s3.amazonaws.com/echo.api/...` (scheme, host, port, and normalised path all enforced).
- Cert chain is fetched + cached in-memory bounded by earliest `notAfter`.
- Leaf cert must be currently valid and include `echo-api.amazon.com` in SAN.
- Body signature verified as RSA-SHA1 over the raw request bytes.
- `request.timestamp` must be within `ALEXA_TIMESTAMP_TOLERANCE_SECONDS` (default 150).

Turn on for production:

```
ALEXA_VERIFY_SIGNATURE=true
```

Covered by `backend/tests/test_alexa_signature.py` (11 tests with self-signed cert fixtures).

## Still to land before Amazon submission

1. **Skill package** (interaction model JSON + endpoint URL). Placeholder env vars: `ALEXA_SKILL_ID`, `ALEXA_CLIENT_ID`, `ALEXA_CLIENT_SECRET`.
2. **Latency guard.** Alexa gives ~8 s per turn. Evaluator + planner are synchronous — fine with the mock provider, but the OpenAI path should be moved to a progressive-response pattern.

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
