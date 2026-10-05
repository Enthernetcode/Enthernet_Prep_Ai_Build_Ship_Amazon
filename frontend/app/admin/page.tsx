"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  ApiError,
  Announcement,
  ProviderConfig,
  SmtpConfig,
} from "../lib/api";
import { RequireAdmin, useAuth } from "../lib/auth";

type Tab = "providers" | "smtp" | "announcements";

function AdminInner() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("providers");

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <nav className="mb-6 flex items-center justify-between text-sm text-eprep-muted">
        <div className="flex gap-4">
          <Link href="/" className="hover:text-eprep-electric">
            Home
          </Link>
          <span>·</span>
          <Link href="/projects" className="hover:text-eprep-electric">
            Projects
          </Link>
        </div>
        <div className="flex items-center gap-3">
          <span>{user?.email}</span>
          <button onClick={logout} className="hover:text-eprep-magenta">
            Log out
          </button>
        </div>
      </nav>

      <header className="mb-6">
        <p className="text-xs uppercase tracking-[0.35em] text-eprep-muted">
          Admin
        </p>
        <h1 className="mt-2 text-3xl font-semibold">Platform settings</h1>
      </header>

      <div className="mb-6 flex gap-2 rounded-md border border-eprep-purple/25 bg-eprep-surface p-1">
        {(["providers", "smtp", "announcements"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-medium capitalize transition ${
              tab === t
                ? "bg-eprep-purple text-white"
                : "text-eprep-muted hover:text-eprep-text"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "providers" && <ProvidersPanel />}
      {tab === "smtp" && <SmtpPanel />}
      {tab === "announcements" && <AnnouncementsPanel />}
    </main>
  );
}

// ─── Providers panel ────────────────────────────────────────────────────────

const PROVIDER_OPTIONS: Array<ProviderConfig["llm_provider"]> = [
  "mock",
  "openai",
  "bedrock",
];

function ProvidersPanel() {
  const [configs, setConfigs] = useState<ProviderConfig[]>([]);
  const [labDraft, setLabDraft] = useState<ProviderConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      setConfigs(await api<ProviderConfig[]>("/admin/providers"));
    } catch (e) {
      setErr(e instanceof ApiError ? String(e.detail ?? e.message) : "Failed");
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const lab = configs.find((c) => c.scope === "lab");
  const judged = configs.find((c) => c.scope === "judged");
  useEffect(() => {
    if (lab) setLabDraft({ ...lab });
  }, [lab]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!labDraft) return;
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      const u = await api<ProviderConfig>("/admin/providers/lab", {
        method: "PUT",
        body: {
          llm_provider: labDraft.llm_provider,
          llm_model: labDraft.llm_model,
          embedding_provider: labDraft.embedding_provider,
          embedding_model: labDraft.embedding_model,
        },
      });
      setLabDraft(u);
      setMsg("Saved. Lab MCP picks this up on the next request.");
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? String(e.detail ?? e.message) : "Failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      {err && <Alert kind="error">{err}</Alert>}
      {msg && <Alert kind="ok">{msg}</Alert>}
      <p className="mb-4 text-sm text-eprep-muted">
        The <em>judged</em> surface at{" "}
        <code className="text-eprep-electric">/api/v1/mcp/</code> is the Alexa+
        submission — read-only. The <em>lab</em> surface at{" "}
        <code className="text-eprep-electric">/api/v1/mcp-lab/</code> honours
        the values you set here.
      </p>
      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-xl border border-eprep-purple/30 bg-eprep-surface p-6">
          <Header title="Judged surface" badge="Locked" tone="lock" />
          <p className="mb-4 text-xs text-eprep-muted">
            Reflects <code>.env</code>. Change via SSH + restart.
          </p>
          {judged ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <Row label="LLM provider" value={judged.llm_provider} />
              <Row label="LLM model" value={judged.llm_model} />
              <Row label="Embed provider" value={judged.embedding_provider} />
              <Row label="Embed model" value={judged.embedding_model} />
            </dl>
          ) : (
            <p className="text-sm text-eprep-muted">Loading…</p>
          )}
        </section>
        <section className="rounded-xl border border-eprep-electric/40 bg-eprep-surface p-6">
          <Header title="Lab surface" badge="Editable" tone="edit" />
          {labDraft ? (
            <form onSubmit={save} className="space-y-3 text-sm">
              <SelectField
                label="LLM provider"
                value={labDraft.llm_provider}
                options={PROVIDER_OPTIONS}
                onChange={(v) => setLabDraft({ ...labDraft, llm_provider: v as any })}
              />
              <TextField
                label="LLM model"
                value={labDraft.llm_model}
                onChange={(v) => setLabDraft({ ...labDraft, llm_model: v })}
              />
              <SelectField
                label="Embedding provider"
                value={labDraft.embedding_provider}
                options={PROVIDER_OPTIONS}
                onChange={(v) =>
                  setLabDraft({ ...labDraft, embedding_provider: v as any })
                }
              />
              <TextField
                label="Embedding model"
                value={labDraft.embedding_model}
                onChange={(v) => setLabDraft({ ...labDraft, embedding_model: v })}
              />
              <button
                type="submit"
                disabled={saving}
                className="w-full rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-40"
              >
                {saving ? "Saving…" : "Save lab config"}
              </button>
            </form>
          ) : (
            <p className="text-sm text-eprep-muted">Loading…</p>
          )}
        </section>
      </div>
    </>
  );
}

// ─── SMTP panel ─────────────────────────────────────────────────────────────

function SmtpPanel() {
  const [smtp, setSmtp] = useState<SmtpConfig | null>(null);
  const [draft, setDraft] = useState<
    (SmtpConfig & { password: string }) | null
  >(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const s = await api<SmtpConfig>("/admin/smtp");
      setSmtp(s);
      setDraft({ ...s, password: "" });
    } catch (e) {
      setErr(e instanceof ApiError ? String(e.detail ?? e.message) : "Failed");
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!draft) return;
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      const u = await api<SmtpConfig>("/admin/smtp", {
        method: "PUT",
        body: {
          enabled: draft.enabled,
          host: draft.host,
          port: draft.port,
          username: draft.username,
          password: draft.password, // empty = keep existing
          from_address: draft.from_address,
          from_name: draft.from_name,
          use_tls: draft.use_tls,
          use_starttls: draft.use_starttls,
        },
      });
      setSmtp(u);
      setDraft({ ...u, password: "" });
      setMsg("Saved.");
    } catch (e) {
      setErr(e instanceof ApiError ? String(e.detail ?? e.message) : "Failed");
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    if (!testTo) return;
    setTesting(true);
    setMsg(null);
    setErr(null);
    try {
      await api("/admin/smtp/test", { body: { to: testTo } });
      setMsg(`Test email sent to ${testTo}.`);
    } catch (e) {
      setErr(e instanceof ApiError ? String(e.detail ?? e.message) : "Failed");
    } finally {
      setTesting(false);
    }
  };

  return (
    <>
      {err && <Alert kind="error">{err}</Alert>}
      {msg && <Alert kind="ok">{msg}</Alert>}
      <p className="mb-4 text-sm text-eprep-muted">
        Outbound email is used for password reset links and (in future)
        admin-triggered notifications. Leave the password field blank on save
        to preserve the one already stored.
      </p>
      {draft ? (
        <form onSubmit={save} className="grid gap-4 md:grid-cols-2">
          <BooleanField
            label="Enabled"
            value={draft.enabled}
            onChange={(v) => setDraft({ ...draft, enabled: v })}
          />
          <TextField
            label="From name"
            value={draft.from_name}
            onChange={(v) => setDraft({ ...draft, from_name: v })}
          />
          <TextField
            label="Host"
            value={draft.host}
            onChange={(v) => setDraft({ ...draft, host: v })}
          />
          <TextField
            label="Port"
            value={String(draft.port)}
            onChange={(v) => setDraft({ ...draft, port: Number(v) || 587 })}
          />
          <TextField
            label="Username"
            value={draft.username}
            onChange={(v) => setDraft({ ...draft, username: v })}
          />
          <TextField
            label={`Password ${draft.password_set ? "(unchanged if blank)" : ""}`}
            value={draft.password}
            onChange={(v) => setDraft({ ...draft, password: v })}
            type="password"
          />
          <TextField
            label="From address"
            value={draft.from_address}
            onChange={(v) => setDraft({ ...draft, from_address: v })}
          />
          <div className="flex items-end gap-4">
            <BooleanField
              label="Use TLS"
              value={draft.use_tls}
              onChange={(v) => setDraft({ ...draft, use_tls: v })}
            />
            <BooleanField
              label="Use STARTTLS"
              value={draft.use_starttls}
              onChange={(v) => setDraft({ ...draft, use_starttls: v })}
            />
          </div>
          <div className="md:col-span-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-40"
            >
              {saving ? "Saving…" : "Save SMTP config"}
            </button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-eprep-muted">Loading…</p>
      )}
      {smtp && (
        <section className="mt-8 rounded-xl border border-eprep-purple/25 bg-eprep-surface p-6">
          <h3 className="mb-2 text-lg font-medium">Send a test email</h3>
          <p className="mb-3 text-sm text-eprep-muted">
            Sends a plain-text message using the config above. Requires{" "}
            <b>Enabled</b>, a host, and a from address.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="email"
              placeholder="recipient@example.com"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              className="flex-1 rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2 text-sm"
            />
            <button
              onClick={sendTest}
              disabled={testing || !testTo}
              className="rounded-md border border-eprep-electric px-4 py-2 text-sm text-eprep-electric hover:bg-eprep-electric/10 disabled:opacity-40"
            >
              {testing ? "Sending…" : "Send test"}
            </button>
          </div>
        </section>
      )}
    </>
  );
}

// ─── Announcements panel ────────────────────────────────────────────────────

function AnnouncementsPanel() {
  const [items, setItems] = useState<Announcement[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [kind, setKind] = useState<Announcement["kind"]>("info");
  const [audience, setAudience] = useState<Announcement["audience"]>("all");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api<Announcement[]>("/admin/announcements"));
    } catch (e) {
      setErr(e instanceof ApiError ? String(e.detail ?? e.message) : "Failed");
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await api<Announcement>("/admin/announcements", {
        body: { title, body, kind, audience, active: true },
      });
      setTitle("");
      setBody("");
      setMsg("Published.");
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? String(e.detail ?? e.message) : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const del = async (id: string) => {
    if (!confirm("Delete this announcement?")) return;
    setBusy(true);
    try {
      await api(`/admin/announcements/${id}`, { method: "DELETE" });
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {err && <Alert kind="error">{err}</Alert>}
      {msg && <Alert kind="ok">{msg}</Alert>}
      <section className="mb-8 rounded-xl border border-eprep-purple/25 bg-eprep-surface p-6">
        <h3 className="mb-3 text-lg font-medium">Publish an announcement</h3>
        <form onSubmit={create} className="grid gap-3 md:grid-cols-4">
          <input
            required
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2 md:col-span-2"
          />
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as any)}
            className="rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2"
          >
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="success">success</option>
          </select>
          <select
            value={audience}
            onChange={(e) => setAudience(e.target.value as any)}
            className="rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2"
          >
            <option value="all">all users</option>
            <option value="admins">admins only</option>
          </select>
          <textarea
            required
            placeholder="Body"
            rows={3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2 md:col-span-4"
          />
          <button
            type="submit"
            disabled={busy || !title || !body}
            className="rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-40 md:col-span-4"
          >
            {busy ? "Working…" : "Publish"}
          </button>
        </form>
      </section>
      <section>
        <h3 className="mb-3 text-lg font-medium">Existing announcements</h3>
        {items.length === 0 && (
          <p className="text-sm text-eprep-muted">None yet.</p>
        )}
        <ul className="space-y-2 text-sm">
          {items.map((a) => (
            <li
              key={a.id}
              className="flex items-start justify-between gap-3 rounded-md border border-eprep-purple/25 bg-eprep-surface p-3"
            >
              <div>
                <p className="font-medium">
                  {a.title}{" "}
                  <span className="ml-2 rounded bg-eprep-bg px-2 py-0.5 text-[10px] uppercase tracking-widest text-eprep-muted">
                    {a.kind} · {a.audience}
                  </span>
                </p>
                <p className="mt-1 text-xs text-eprep-muted">{a.body}</p>
              </div>
              <button
                onClick={() => del(a.id)}
                className="text-xs text-eprep-magenta hover:text-eprep-electric"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

// ─── Small UI atoms ─────────────────────────────────────────────────────────

function Header({
  title,
  badge,
  tone,
}: {
  title: string;
  badge: string;
  tone: "lock" | "edit";
}) {
  const cls =
    tone === "lock"
      ? "bg-eprep-purple/30 text-eprep-electric"
      : "bg-eprep-electric/20 text-eprep-electric";
  return (
    <div className="mb-4 flex items-center justify-between">
      <h2 className="text-lg font-semibold">{title}</h2>
      <span
        className={`rounded px-2 py-0.5 text-[10px] uppercase tracking-widest ${cls}`}
      >
        {badge}
      </span>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-xs uppercase tracking-widest text-eprep-muted">
        {label}
      </dt>
      <dd className="text-right font-medium text-eprep-text">{value}</dd>
    </>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-widest text-eprep-muted">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-widest text-eprep-muted">
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2 font-mono text-sm"
      />
    </label>
  );
}

function BooleanField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-eprep-text">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-eprep-purple/50 bg-eprep-bg"
      />
      {label}
    </label>
  );
}

function Alert({
  children,
  kind,
}: {
  children: React.ReactNode;
  kind: "ok" | "error";
}) {
  const cls =
    kind === "ok"
      ? "border-eprep-electric/40 bg-eprep-electric/10 text-eprep-electric"
      : "border-eprep-magenta/40 bg-eprep-magenta/10 text-eprep-magenta";
  return (
    <p className={`mb-4 rounded-md border px-4 py-3 text-sm ${cls}`}>
      {children}
    </p>
  );
}

export default function AdminHubPage() {
  return (
    <RequireAdmin>
      <AdminInner />
    </RequireAdmin>
  );
}
