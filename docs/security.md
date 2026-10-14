# Security

Current security posture of Enthernet Prep AI. Written against the shipping code, not aspirations.

## Authentication

- **Argon2** password hashing via `argon2-cffi` (`app/auth/__init__.py`).
- **JWT access tokens** signed with `settings.app_secret`, algorithm from `settings.jwt_algorithm` (HS256 default), TTL from `settings.jwt_access_token_minutes` (default 60).
- `get_current_user` dependency decodes + validates every protected request.
- Password reset: one-time **SHA-256-hashed** tokens with 30-minute expiry, stored in `password_reset_tokens` (plaintext never persisted). `/auth/forgot-password` returns the same body for known/unknown emails to prevent account enumeration. See `app/api/v1/auth.py` + `test_password_reset.py`.

## Data isolation (§16)

Every resource query joins against `user_id` (and `project_id` where applicable) derived from the authenticated JWT. Never from client-supplied body/path parameters.

- `app/api/v1/documents.py:_load_owned_document`: joins Document → PreparationProject → User.
- `app/api/v1/retrieval.py`: scopes vector search to the user's project only.
- `app/api/v1/sessions.py:_load_owned_session`: joins PreparationSession → PreparationProject → User.
- `app/api/v1/competencies.py`, `app/api/v1/readiness.py`. ownership check on every call.

Covered by cross-user tests: `test_projects.py::test_user_isolation`, `test_documents.py::test_cross_user_document_hidden`, `test_retrieval.py::test_retrieval_cross_user_forbidden`, `test_session_loop.py::test_session_isolated_across_users`.

## Uploads (§18, §19)

- MIME allow-list (`settings.document_allowed_mimes`): PDF, DOCX, TXT, Markdown.
- Hard size cap: `settings.document_max_size_bytes` (default 25 MiB) → HTTP 413.
- **Server-generated filenames**: `storage_key = f"projects/{project_id}/{uuid.uuid4()}{extension}"`. Client-supplied `filename` is stored as metadata only, never used for filesystem paths.
- Presigned-URL downloads with short TTL (`settings.document_presign_ttl_seconds`, default 300 s).
- Document content is treated as **data, not instructions** (§19). Agents operate on extracted text + embeddings; nothing in a document body can elevate privilege or redirect agent policy.

## Admin surface

- Gated by `settings.admin_emails` (JSON array of email addresses). Non-admin requests to `/admin/*` return HTTP 403.
- Admin endpoints only accept **provider names** (`mock` / `openai` / `bedrock`) and **model names**: never API keys. Keys live exclusively in `.env`.
- SMTP password is stored at rest in the `smtp_configs` table but is **never returned** in any response (the `password_set: bool` flag is the only signal). Blank-password save preserves the existing value.

## Alexa webhook

Two paths, selected by `settings.alexa_verify_signature`:

- `false` (default, demo mode). accepts Bearer-authed requests from any caller for easy testing.
- `true` (prod/cert mode). enforces Amazon's full request-signature spec (`app/alexa/verify.py`): HTTPS cert chain URL validation, cert chain fetch + cache, SAN check for `echo-api.amazon.com`, RSA-SHA1 signature verification over the raw request body, and a 150-second timestamp window. 11 tests in `test_alexa_signature.py` exercise self-signed cert fixtures + every rejection path (bad scheme, wrong host, path traversal, wrong SAN, expired cert, tampered body, stale timestamp).

## MCP endpoints

- Both `/api/v1/mcp/` and `/api/v1/mcp-lab/` require `Authorization: Bearer <jwt>` on every tool call. The MCP `initialize` handshake is public (the server identifies itself and advertises its spec version), but `tools/call` is auth-gated.
- Stateless HTTP transport (`stateless_http=True`): no sticky session, each request is independent.
- Lab-only `X-LLM-Provider` header lets admins (and judges) switch providers per request. The resolver still falls back through DB config → settings, so an unauthorized header value doesn't execute arbitrary code. just picks between the three built-in providers.

## Error surfaces

- 401 / 403 / 404 responses carry a `detail` field with a short, non-sensitive reason string. Stack traces, SQL fragments, provider SDK errors, and file paths are not surfaced to clients.
- Internal errors in background ingest write to `document.error` (truncated to 1000 chars) so the UI can show a user-friendly state without leaking traces.

## Secret hygiene

- `.env` is `.gitignore`d.
- `.env.example` ships placeholder values (`change-me-to-a-long-random-string`, `eprep-minio` etc.) that are obvious non-secrets.
- Production VPS `.env` is populated with rotated secrets via `openssl rand -hex 32` at deploy time (see `docs/cheatsheet.md`).

## Non-goals / explicitly deferred

- Rate limiting at the API layer (nginx is the only edge limiter today).
- MFA, email verification before login, OAuth2 account linking for the web app.
- Alexa+ account linking via Login-with-Amazon (webhook today accepts the same JWT the web app issues).
- Scanning uploaded binaries for malware beyond MIME + size checks.
