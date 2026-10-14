# Friction log: Build, Ship, Shape (Amazon Developer Hackathon)

Per the submission-rules bonus criterion: for each Amazon tool / API / SDK we used, this is what happened, what worked, what didn't, and one concrete suggestion.

---

## Entry 1: Alexa+ Developer Console (Agent Skills path)

**Task attempted:** Register a first-party Alexa+ Agent Skill so the same Prep AI engine could be exposed as a native Alexa+ integration in addition to the MCP server.

**Steps taken:** Signed in to `developer.amazon.com`, opened the top-of-page "Alexa+ Developer Console" tile → *Create and manage your add-on*.

**Expected vs. actual:** Expected an add-on creation form. Got a white page saying **"coming soon"**. No visible link to a private preview, allowlist request, or roadmap.

**Severity:** *Important*. The hackathon rules explicitly name Agent Skills as one of two primary integration options for the Alexa+ track, but the console needed to build one isn't publicly available.

**Workaround:** Pivoted the entire integration to a self-hosted MCP server (spec 2025-11-25, Streamable HTTP), the other primary option for the track. Not a regression (MCP is arguably a better fit for an agentic tool), but the wasted discovery time was real.

**Suggestion:** On the Amazon Developer landing page, replace the "Alexa+ Developer Console" tile's link with an inline "Preview access required — request access here" affordance while the console remains gated. If Agent Skills won't be publicly registerable during the hackathon window, say so in the hackathon rules under *Requirements → Alexa+*.

---

## Entry 2: Alexa Skills Kit console (fallback path we didn't submit)

**Task attempted:** Point a classic ASK custom skill at our webhook as a fallback demo surface.

**Steps taken:** Created the skill via ASK console → JSON interaction model with three intents (`StartInterviewIntent`, `AnswerIntent`, `FinalBossIntent`) plus the standard Amazon ones → Endpoint set to a Cloudflare tunnel URL.

**What worked well:** Simulator's *Access Token* field made it trivial to hand-carry a JWT for the demo without building a full OAuth flow. Documentation for classic ASK is excellent.

**What needs work:** Not obvious from the ASK console that classic skills **don't** count for the Alexa+ track prize submission. We wasted ~30 minutes here before rereading the hackathon requirements and pivoting to MCP. A one-line banner on the ASK console's *Create Skill* page saying *"For the Amazon Developer Hackathon Alexa+ track, use the MCP server or Agent Skill option, not a classic custom skill"* would have saved that time.

**Severity:** *Nice-to-have*.

---

## Entry 3: MCP Python SDK (`mcp` on PyPI, v2.2)

**Task attempted:** Build a Streamable HTTP MCP server mounted under FastAPI at `/api/v1/mcp/`.

**What worked well:**
- `MCPServer.tool` decorator with type-annotated arg parsing is very ergonomic. 7 tools registered with zero boilerplate.
- `streamable_http_app(...)` returns a Starlette ASGI app that mounts cleanly under FastAPI.
- Structured content pass-through: returning a plain `dict` from a tool becomes a `structuredContent` block on the client side without any explicit serialization.
- Test with `ASGITransport` + `session_manager.run()` in a lifespan fixture. no need to spin up a real server.

**What needs work:**
- **v1 → v2 migration is confusing.** The SDK renamed `FastMCP` → `MCPServer` and moved several imports (`mcp.shared.exceptions.McpError` → `MCPError`, plus a new `mcp.server.mcpserver.exceptions.ToolError`). The migration guide URL surfaces in the error message, which is great, but the *examples* in the primary README still show v1 shapes.
- **`session_manager` is lazy-initialised** only after `streamable_http_app()` is called, and refuses a second `.run()` on the same instance. That's fine in production (single lifespan) but surprising in tests. I had to swap to `asgi-lifespan` and a session-scoped fixture to keep it happy. A `MCPServer.reset()` method for tests would remove that footgun.
- The `httpx2` fork is pulled in as a hard dep and adds a second HTTP client to the process alongside `httpx`. Two HTTP client stacks in one image doubles the surface for connection-pool bugs.

**Severity:** *Nice-to-have*. The SDK works, just not obvious.

**Suggestion:** Add a "Mount under FastAPI" section to the docs with the exact `app.mount("/mcp", server.streamable_http_app(streamable_http_path='/'))` + lifespan snippet. Would have saved 20 minutes of trial-and-error.

---

## Entry 4: AWS Bedrock (via `boto3.client('bedrock-runtime')`)

**Task attempted:** Add a `BedrockLLMProvider` and `BedrockEmbeddingProvider` to our provider abstraction so `LLM_PROVIDER=bedrock` swaps in Claude on Bedrock without other code changes.

**What worked well:** The `converse` API is model-agnostic. One code path handles Anthropic, Meta, Titan, Cohere, and Mistral. `inferenceConfig` is a clean spot for `maxTokens`/`temperature` without model-specific request shapes.

**What needs work:**
- **Model-id inconsistency between embeddings and inference.** Chat/Converse uses cross-region IDs like `us.anthropic.claude-3-5-sonnet-20241022-v2:0`; embeddings use bare IDs like `amazon.titan-embed-text-v2:0`. Either everywhere-cross-region or a `Bedrock.resolve_model_id()` helper would fix it.
- **Embedding request body shape differs by provider family** (Titan vs Cohere) even inside `invoke_model`. we ended up branching on the model-id prefix.

**Severity:** *Nice-to-have*.

**Suggestion:** A unified `bedrock-runtime.embed()` action that takes provider-family-agnostic input, mirroring how `converse` unified the chat side.

---

## Entry 5: MinIO (S3-compatible, for our local dev pipeline)

Not an Amazon service, but relevant to why the switch to real S3 will Just Work: MinIO's boto3 compatibility is total. Zero code change between MinIO and S3 endpoints for `put_object` / `get_object` / presigned URLs. Kudos for the SDK stability that makes this possible.

**Severity:** *Nice-to-have*. Feedback for AWS/S3 team: keep the SDK stable, third-party server implementations rely on it.

---

## Features we'd like built

- **Alexa+ Add-on emulator (like the ASK simulator)**: being able to test an add-on locally before the developer console is public would be a massive unblock. **Severity: Critical** for anyone building against the Alexa+ track in this hackathon window.
- **`bedrock-runtime.embed()` unified action**: see Entry 4. **Severity: Important**.
- **MCP SDK "mount under FastAPI" example in the primary docs**: see Entry 3. **Severity: Nice-to-have**.
