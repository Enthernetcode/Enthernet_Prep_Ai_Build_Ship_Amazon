# Security

Authoritative source: `AGENT.md` §14, §16, §18–19, §41–43, §45, §62, §68–70.

## Non-negotiables (enforce from the first real feature)

- **Data isolation:** every query joins `user_id` + `project_id` from server-authenticated context. Never trust client-supplied IDs (§16).
- **Uploads are data, not instructions:** Document content flows into embeddings/retrieval; it never influences agent policy (§19).
- **Least-privilege agent tools:** each agent receives only the tools listed for it in §13. Tool gateway (§14) enforces auth + timeout + logging.
- **Secrets:** `.env` only in dev; AWS Secrets Manager (or equivalent) in prod. `.env` is git-ignored (§43).
- **Structured errors:** never leak stack traces, SQL, provider errors, or filesystem paths to clients (§45).

## Scaffold posture

- CORS allows `http://localhost:3000` only.
- No auth yet — all `/api/v1/*` resource endpoints return 501 to prevent accidental data exposure via unauthenticated stubs.
- MinIO credentials in `.env.example` are placeholders; change them on any host reachable from a network.

## To be added

- Password hashing (argon2 or bcrypt), rate limiting, session cookies with `Secure`+`HttpOnly`+`SameSite=Lax`.
- Upload validation: MIME sniff, extension whitelist, size cap, malware scan hook, server-generated filenames (§18).
- Prompt-injection tests against uploaded content (§62).
- Deletion cascade for projects → documents → chunks → embeddings → sessions → evaluations (§70).
