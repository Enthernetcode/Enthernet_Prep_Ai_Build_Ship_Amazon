"use client";

/**
 * Built-in MCP client page.
 *
 * Per the Devpost FAQ, "a web page that acts as an actual MCP client (sending
 * initialize, tools-list, and tools-call requests over Streamable HTTP)
 * satisfies the requirement." This page is exactly that — judges open it in a
 * browser and exercise the MCP server end-to-end with no external software
 * (no Claude Desktop, no curl, no SDK).
 *
 * Flow handled automatically:
 *   1. Mint a demo JWT via POST /api/v1/demo/seed (no login).
 *   2. POST initialize → capture `mcp-session-id` from the response headers.
 *   3. POST notifications/initialized.
 *   4. POST tools/list → render each tool as a card with a per-tool form.
 *   5. POST tools/call on form submit → show the structured + raw response.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { API_BASE } from "../lib/api";

type Endpoint = "judged" | "lab";

interface ToolDef {
  name: string;
  description?: string;
  inputSchema?: {
    properties?: Record<string, { type?: string; description?: string; default?: unknown }>;
    required?: string[];
  };
}

interface LogEntry {
  dir: "→" | "←";
  method?: string;
  ok?: boolean;
  text: string;
}

// Strip the API path from API_BASE to get the server origin (e.g.
// http://localhost:8000) — the two MCP mounts live below that.
function serverOrigin(): string {
  try {
    const u = new URL(API_BASE);
    return `${u.protocol}//${u.host}`;
  } catch {
    return "http://localhost:8000";
  }
}

const ENDPOINT_PATH: Record<Endpoint, string> = {
  judged: "/api/v1/mcp/",
  lab: "/api/v1/mcp-lab/",
};

function parseResponse(bodyText: string): unknown {
  // Streamable HTTP returns either application/json or an SSE stream whose
  // first (and in practice only) `data:` line is the JSON-RPC response.
  for (const line of bodyText.split("\n")) {
    if (line.startsWith("data:")) {
      try {
        return JSON.parse(line.slice("data:".length).trim());
      } catch {
        /* fallthrough */
      }
    }
  }
  try {
    return JSON.parse(bodyText);
  } catch {
    return bodyText;
  }
}

function unwrapToolResult(result: any): unknown {
  if (!result) return result;
  if (result.structuredContent) return result.structuredContent;
  for (const block of result.content ?? []) {
    if (block.type === "text") {
      try {
        return JSON.parse(block.text);
      } catch {
        return block.text;
      }
    }
  }
  return result;
}

export default function MCPTesterPage() {
  const origin = useMemo(() => serverOrigin(), []);
  const [endpoint, setEndpoint] = useState<Endpoint>("judged");
  const [token, setToken] = useState("");
  // Our MCP server mounts stateless_http=True, so the response to initialize
  // typically does NOT carry an `mcp-session-id` header. We still track it in
  // case the server starts sending one, but gate step 3/4 on `initialized`.
  const [sessionId, setSessionId] = useState("");
  const [initialized, setInitialized] = useState(false);
  const [tools, setTools] = useState<ToolDef[]>([]);
  const [args, setArgs] = useState<Record<string, Record<string, string>>>({});
  const [toolResult, setToolResult] = useState<Record<string, unknown>>({});
  const [providerHeader, setProviderHeader] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const url = `${origin}${ENDPOINT_PATH[endpoint]}`;

  const appendLog = useCallback((entry: LogEntry) => {
    setLog((prev) => [...prev.slice(-50), entry]);
  }, []);

  const headers = useCallback(
    (withSession: boolean, withProviderHeader = false): Headers => {
      const h = new Headers();
      h.set("Content-Type", "application/json");
      h.set("Accept", "application/json, text/event-stream");
      if (token) h.set("Authorization", `Bearer ${token}`);
      if (withSession && sessionId) h.set("mcp-session-id", sessionId);
      if (withProviderHeader && endpoint === "lab" && providerHeader) {
        h.set("X-LLM-Provider", providerHeader);
      }
      return h;
    },
    [token, sessionId, providerHeader, endpoint],
  );

  const postJsonRpc = useCallback(
    async (
      method: string,
      params: unknown = {},
      opts: { captureSession?: boolean; withProviderHeader?: boolean } = {},
    ): Promise<unknown> => {
      const body = JSON.stringify({
        jsonrpc: "2.0",
        id: Date.now(),
        method,
        params,
      });
      appendLog({ dir: "→", method, text: body });
      const resp = await fetch(url, {
        method: "POST",
        headers: headers(!opts.captureSession ? true : false, opts.withProviderHeader),
        body,
      });
      if (opts.captureSession) {
        const sid = resp.headers.get("mcp-session-id");
        if (sid) setSessionId(sid);
      }
      const text = await resp.text();
      appendLog({ dir: "←", ok: resp.ok, text });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }
      return parseResponse(text);
    },
    [url, headers, appendLog],
  );

  // ─── Actions ──────────────────────────────────────────────────────────

  const mintToken = async () => {
    setBusy("token");
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/demo/seed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const payload = await resp.json();
      if (!resp.ok) throw new Error(payload.detail ?? `HTTP ${resp.status}`);
      setToken(payload.access_token);
      appendLog({
        dir: "←",
        ok: true,
        text: `demo/seed → token for project ${payload.project_id} (${payload.competencies} competencies, baseline ${(payload.baseline_readiness * 100).toFixed(0)}%)`,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const initialize = async () => {
    if (!token) {
      setError("Mint a token first.");
      return;
    }
    setBusy("init");
    setError(null);
    try {
      await postJsonRpc(
        "initialize",
        {
          protocolVersion: "2025-11-25",
          capabilities: {},
          clientInfo: { name: "mcp-tester-web", version: "1.0.0" },
        },
        { captureSession: true },
      );
      // The server requires the initialized notification before accepting
      // tools/list — do it immediately.
      await fetch(url, {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({
          jsonrpc: "2.0",
          method: "notifications/initialized",
          params: {},
        }),
      });
      appendLog({ dir: "→", method: "notifications/initialized", text: "{}" });
      setInitialized(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const listTools = async () => {
    if (!initialized) {
      setError("Initialize the session first.");
      return;
    }
    setBusy("list");
    setError(null);
    try {
      const body = (await postJsonRpc("tools/list")) as any;
      const list: ToolDef[] = body?.result?.tools ?? [];
      setTools(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const callTool = async (tool: ToolDef) => {
    if (!initialized) {
      setError("Initialize first.");
      return;
    }
    setBusy(tool.name);
    setError(null);
    try {
      // Coerce arg values based on the tool's inputSchema.
      const raw = args[tool.name] ?? {};
      const props = tool.inputSchema?.properties ?? {};
      const coerced: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(raw)) {
        if (v === "") continue;
        const t = props[k]?.type;
        if (t === "integer" || t === "number") coerced[k] = Number(v);
        else if (t === "boolean") coerced[k] = v === "true";
        else coerced[k] = v;
      }
      const body = (await postJsonRpc(
        "tools/call",
        { name: tool.name, arguments: coerced },
        { withProviderHeader: true },
      )) as any;
      setToolResult((prev) => ({ ...prev, [tool.name]: unwrapToolResult(body?.result) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  // Reset session when switching endpoint.
  useEffect(() => {
    setSessionId("");
    setInitialized(false);
    setTools([]);
    setToolResult({});
  }, [endpoint]);

  // ─── UI ───────────────────────────────────────────────────────────────

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <nav className="mb-6 text-sm text-eprep-muted">
        <Link href="/" className="hover:text-eprep-electric">
          ← Home
        </Link>
      </nav>

      <header className="mb-6">
        <p className="text-xs uppercase tracking-[0.35em] text-eprep-muted">
          Alexa+ track · built-in MCP client
        </p>
        <h1 className="mt-2 text-3xl font-semibold">MCP tester</h1>
        <p className="mt-2 text-sm text-eprep-muted">
          A browser-only MCP client (spec 2025-11-25, Streamable HTTP). Press
          the four buttons in order — mint a token, initialize, list tools,
          then invoke any <code>prep.*</code> tool. No API keys, no external
          software required.
        </p>
      </header>

      {/* Endpoint selector + status */}
      <section className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-eprep-purple/30 bg-eprep-surface p-4">
        <div className="flex gap-1 rounded-md border border-eprep-purple/40 p-1">
          {(["judged", "lab"] as Endpoint[]).map((e) => (
            <button
              key={e}
              onClick={() => setEndpoint(e)}
              className={`rounded px-3 py-1 text-sm transition ${
                endpoint === e
                  ? "bg-eprep-purple text-white"
                  : "text-eprep-muted hover:text-eprep-text"
              }`}
            >
              {e === "judged" ? "judged (/api/v1/mcp/)" : "lab (/api/v1/mcp-lab/)"}
            </button>
          ))}
        </div>
        <code className="text-xs text-eprep-muted">POST {url}</code>
        {initialized && (
          <span className="rounded bg-eprep-electric/20 px-2 py-0.5 text-[10px] uppercase tracking-widest text-eprep-electric">
            {sessionId ? `session: ${sessionId.slice(0, 8)}…` : "initialized (stateless)"}
          </span>
        )}
        {endpoint === "lab" && (
          <label className="ml-auto flex items-center gap-2 text-xs text-eprep-muted">
            X-LLM-Provider override:
            <select
              value={providerHeader}
              onChange={(e) => setProviderHeader(e.target.value)}
              className="rounded border border-eprep-purple/40 bg-eprep-bg px-2 py-1 text-eprep-text"
            >
              <option value="">(none — use default)</option>
              <option value="mock">mock</option>
              <option value="openai">openai</option>
              <option value="bedrock">bedrock</option>
            </select>
          </label>
        )}
      </section>

      {/* 4-step action strip */}
      <section className="mb-6 grid gap-3 md:grid-cols-4">
        <Step
          num={1}
          label="Mint a demo token"
          onClick={mintToken}
          disabled={busy !== null}
          done={!!token}
          busy={busy === "token"}
          hint={token ? `${token.slice(0, 12)}…` : "no login required"}
        />
        <Step
          num={2}
          label="Initialize MCP session"
          onClick={initialize}
          disabled={busy !== null || !token}
          done={initialized}
          busy={busy === "init"}
          hint={initialized ? "ready" : "sends initialize + initialized"}
        />
        <Step
          num={3}
          label="List tools"
          onClick={listTools}
          disabled={busy !== null || !initialized}
          done={tools.length > 0}
          busy={busy === "list"}
          hint={tools.length ? `${tools.length} tools` : "tools/list"}
        />
        <Step
          num={4}
          label="Invoke a tool"
          disabled
          done={false}
          busy={false}
          hint="pick one below"
        />
      </section>

      {error && (
        <p className="mb-4 rounded-md border border-eprep-magenta/40 bg-eprep-magenta/10 px-4 py-3 text-sm text-eprep-magenta">
          {error}
        </p>
      )}

      {/* Tool cards */}
      {tools.length > 0 && (
        <section className="mb-8 grid gap-4 md:grid-cols-2">
          {tools.map((tool) => (
            <ToolCard
              key={tool.name}
              tool={tool}
              values={args[tool.name] ?? {}}
              onChange={(k, v) =>
                setArgs((prev) => ({
                  ...prev,
                  [tool.name]: { ...(prev[tool.name] ?? {}), [k]: v },
                }))
              }
              onCall={() => callTool(tool)}
              busy={busy === tool.name}
              lastResult={toolResult[tool.name]}
            />
          ))}
        </section>
      )}

      {/* Raw log */}
      <details
        open={log.length < 6}
        className="rounded-xl border border-eprep-purple/20 bg-eprep-surface p-4"
      >
        <summary className="cursor-pointer text-sm text-eprep-muted">
          Raw wire log ({log.length})
        </summary>
        <pre className="mt-3 max-h-72 overflow-auto rounded bg-eprep-bg p-3 font-mono text-xs text-eprep-text">
          {log.length === 0
            ? "(nothing yet — press 1 → 2 → 3 above)"
            : log
                .map(
                  (e) =>
                    `${e.dir} ${e.method ?? ""} ${e.ok === false ? "ERR" : ""}\n   ${e.text.slice(0, 400)}`,
                )
                .join("\n\n")}
        </pre>
      </details>
    </main>
  );
}

// ─── UI atoms ──────────────────────────────────────────────────────────────

function Step({
  num,
  label,
  onClick,
  disabled,
  done,
  busy,
  hint,
}: {
  num: number;
  label: string;
  onClick?: () => void;
  disabled: boolean;
  done: boolean;
  busy: boolean;
  hint: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || !onClick}
      className={`rounded-xl border p-3 text-left transition ${
        done
          ? "border-eprep-electric/60 bg-eprep-electric/10"
          : "border-eprep-purple/30 bg-eprep-surface hover:border-eprep-electric/40"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      <div className="flex items-baseline gap-2">
        <span className="bg-gradient-to-br from-eprep-magenta to-eprep-electric bg-clip-text text-xl font-bold text-transparent">
          0{num}
        </span>
        <span className="text-sm font-medium">{busy ? "Working…" : label}</span>
      </div>
      <p className="mt-1 text-xs text-eprep-muted">{hint}</p>
    </button>
  );
}

function ToolCard({
  tool,
  values,
  onChange,
  onCall,
  busy,
  lastResult,
}: {
  tool: ToolDef;
  values: Record<string, string>;
  onChange: (k: string, v: string) => void;
  onCall: () => void;
  busy: boolean;
  lastResult: unknown;
}) {
  const props = tool.inputSchema?.properties ?? {};
  const required = new Set(tool.inputSchema?.required ?? []);
  const keys = Object.keys(props);

  return (
    <article className="rounded-xl border border-eprep-purple/25 bg-eprep-surface p-5">
      <h3 className="font-mono text-sm font-semibold text-eprep-electric">
        {tool.name}
      </h3>
      {tool.description && (
        <p className="mt-1 text-xs leading-relaxed text-eprep-muted">
          {tool.description}
        </p>
      )}

      {keys.length > 0 ? (
        <div className="mt-3 space-y-2">
          {keys.map((k) => {
            const p = props[k];
            return (
              <label key={k} className="block text-xs">
                <span className="text-eprep-muted">
                  {k}
                  {required.has(k) && <span className="text-eprep-magenta"> *</span>}
                  <span className="ml-1 text-[10px] opacity-60">({p.type ?? "any"})</span>
                </span>
                <input
                  type="text"
                  value={values[k] ?? ""}
                  onChange={(e) => onChange(k, e.target.value)}
                  placeholder={typeof p.default !== "undefined" ? String(p.default) : ""}
                  className="mt-1 w-full rounded border border-eprep-purple/40 bg-eprep-bg px-2 py-1 font-mono text-xs text-eprep-text"
                />
                {p.description && (
                  <span className="mt-1 block text-[10px] text-eprep-muted/80">
                    {p.description}
                  </span>
                )}
              </label>
            );
          })}
        </div>
      ) : (
        <p className="mt-3 text-xs italic text-eprep-muted">No arguments.</p>
      )}

      <button
        onClick={onCall}
        disabled={busy}
        className="mt-4 w-full rounded-md bg-eprep-purple px-3 py-1.5 text-sm font-medium text-white hover:bg-eprep-magenta disabled:opacity-40"
      >
        {busy ? "Calling…" : "Call tool"}
      </button>

      {lastResult !== undefined && (
        <pre className="mt-3 max-h-56 overflow-auto rounded bg-eprep-bg p-2 font-mono text-[10px] text-eprep-text">
          {typeof lastResult === "string"
            ? lastResult
            : JSON.stringify(lastResult, null, 2)}
        </pre>
      )}
    </article>
  );
}
