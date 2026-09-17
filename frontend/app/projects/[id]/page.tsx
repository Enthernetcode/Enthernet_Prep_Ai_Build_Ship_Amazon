"use client";

import { ChangeEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { RequireAuth } from "../../lib/auth";
import {
  api,
  ApiError,
  Competency,
  DocumentSummary,
  Project,
  Readiness,
  SessionDetail,
} from "../../lib/api";

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

function DashboardInner() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [competencies, setCompetencies] = useState<Competency[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [sessions, setSessions] = useState<SessionDetail[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [p, docs, comps, sess] = await Promise.all([
        api<Project>(`/projects/${projectId}`),
        api<DocumentSummary[]>(`/projects/${projectId}/documents/`),
        api<Competency[]>(`/projects/${projectId}/competencies/`),
        api<SessionDetail[]>(`/projects/${projectId}/sessions/`),
      ]);
      setProject(p);
      setDocuments(docs);
      setCompetencies(comps);
      setSessions(sess);
      try {
        setReadiness(await api<Readiness>(`/projects/${projectId}/readiness/`));
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 404) throw e;
        setReadiness(null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed");
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await api<DocumentSummary>(`/projects/${projectId}/documents/`, { form });
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Upload failed");
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  const runExtract = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${projectId}/competencies/extract`, { method: "POST" });
      await api(`/projects/${projectId}/readiness/baseline`, { method: "POST" });
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Extract failed");
    } finally {
      setBusy(false);
    }
  };

  const startSession = async (mode: "mock_interview" | "final_boss") => {
    setBusy(true);
    setError(null);
    try {
      const sess = await api<SessionDetail>(`/projects/${projectId}/sessions/`, {
        body: { mode, difficulty: mode === "final_boss" ? 5 : 3 },
      });
      router.push(`/projects/${projectId}/sessions/${sess.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Start failed");
    } finally {
      setBusy(false);
    }
  };

  if (!project) {
    return (
      <div className="flex min-h-screen items-center justify-center text-eprep-muted">
        {error ? <span className="text-eprep-magenta">{error}</span> : "Loading…"}
      </div>
    );
  }

  const anyProcessing = documents.some((d) => d.status !== "processed" && d.status !== "failed");
  const canExtract = documents.some((d) => d.status === "processed");
  const canStart = competencies.length > 0;

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <nav className="mb-6 text-sm text-eprep-muted">
        <Link href="/projects" className="hover:text-eprep-electric">
          ← All projects
        </Link>
      </nav>
      <header className="mb-8 flex items-start justify-between gap-6">
        <div>
          <p className="text-xs uppercase tracking-widest text-eprep-muted">
            {project.goal_type.replaceAll("_", " ")}
          </p>
          <h1 className="text-3xl font-semibold">{project.name}</h1>
          <p className="text-sm text-eprep-muted">
            Target date: {project.target_date ?? "unspecified"} · difficulty {project.difficulty}
          </p>
        </div>
        {readiness && (
          <div className="rounded-xl border border-eprep-electric/40 bg-eprep-surface px-6 py-4 text-right">
            <p className="text-xs uppercase tracking-widest text-eprep-muted">Readiness</p>
            <p className="text-4xl font-bold text-eprep-electric">{pct(readiness.overall)}</p>
            <p className="text-xs text-eprep-muted">source: {readiness.source}</p>
          </div>
        )}
      </header>

      {error && <p className="mb-4 text-sm text-eprep-magenta">{error}</p>}

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-xl border border-eprep-purple/30 bg-eprep-surface p-6">
          <h2 className="mb-3 text-lg font-medium">1. Upload materials</h2>
          <p className="mb-3 text-sm text-eprep-muted">
            CV, JD, and any other context (PDF, DOCX, TXT, MD).
          </p>
          <label className="block cursor-pointer rounded-md border border-dashed border-eprep-purple/60 p-4 text-center text-sm text-eprep-muted hover:border-eprep-electric">
            <input type="file" onChange={onUpload} disabled={busy} className="hidden" />
            {busy ? "Uploading…" : "Click to upload a document"}
          </label>
          <ul className="mt-4 space-y-2 text-sm">
            {documents.map((d) => (
              <li key={d.id} className="flex justify-between rounded-md bg-eprep-bg px-3 py-2">
                <span>{d.filename}</span>
                <span
                  className={
                    d.status === "processed"
                      ? "text-eprep-electric"
                      : d.status === "failed"
                        ? "text-eprep-magenta"
                        : "text-eprep-muted"
                  }
                >
                  {d.status}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-xl border border-eprep-purple/30 bg-eprep-surface p-6">
          <h2 className="mb-3 text-lg font-medium">2. Competency map</h2>
          <p className="mb-3 text-sm text-eprep-muted">
            Extract skills, technologies, and claims from your documents.
          </p>
          <button
            onClick={runExtract}
            disabled={!canExtract || busy}
            className="rounded-md bg-eprep-purple px-4 py-2 text-sm font-medium text-white hover:bg-eprep-magenta disabled:opacity-40"
          >
            {competencies.length > 0 ? "Re-extract" : "Extract now"}
          </button>
          {anyProcessing && (
            <p className="mt-2 text-xs text-eprep-muted">Some documents are still ingesting…</p>
          )}
          <ul className="mt-4 max-h-64 space-y-1 overflow-y-auto text-xs">
            {competencies.slice(0, 40).map((c) => (
              <li key={c.id} className="flex justify-between rounded bg-eprep-bg px-2 py-1">
                <span>
                  <span className="text-eprep-muted">[{c.kind}]</span> {c.label}
                </span>
                <span className="text-eprep-muted">mastery {pct(c.mastery)}</span>
              </li>
            ))}
            {competencies.length > 40 && (
              <li className="pt-1 text-eprep-muted">…and {competencies.length - 40} more</li>
            )}
          </ul>
        </section>
      </div>

      {readiness && (
        <section className="mt-6 rounded-xl border border-eprep-electric/30 bg-eprep-surface p-6">
          <h2 className="mb-4 text-lg font-medium">Readiness breakdown</h2>
          <div className="grid grid-cols-3 gap-4 text-sm md:grid-cols-6">
            {(
              [
                ["Knowledge", readiness.knowledge],
                ["Comms", readiness.communication],
                ["Evidence", readiness.evidence],
                ["Conciseness", readiness.conciseness],
                ["Pressure", readiness.pressure],
                ["Consistency", readiness.consistency],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="rounded bg-eprep-bg p-3">
                <p className="text-xs uppercase text-eprep-muted">{label}</p>
                <p className="text-xl font-semibold">{pct(value)}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-eprep-muted">Coverage: {pct(readiness.coverage)}</p>
        </section>
      )}

      <section className="mt-6 rounded-xl border border-eprep-purple/30 bg-eprep-surface p-6">
        <h2 className="mb-3 text-lg font-medium">3. Practice</h2>
        <p className="mb-4 text-sm text-eprep-muted">
          Mock interview lets you learn with hints. Final Boss is the graded assessment — no hints, longer, and it produces your final report.
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => startSession("mock_interview")}
            disabled={!canStart || busy}
            className="rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-40"
          >
            Start mock interview
          </button>
          <button
            onClick={() => startSession("final_boss")}
            disabled={!canStart || busy}
            className="rounded-md border border-eprep-electric px-4 py-2 font-medium text-eprep-electric hover:bg-eprep-electric/10 disabled:opacity-40"
          >
            Final Boss
          </button>
        </div>
        {!canStart && (
          <p className="mt-2 text-xs text-eprep-muted">
            Extract competencies first.
          </p>
        )}
        {sessions.length > 0 && (
          <ul className="mt-6 space-y-2 text-sm">
            {sessions.map((s) => (
              <li key={s.id}>
                <Link
                  href={
                    s.status === "completed"
                      ? `/projects/${projectId}/sessions/${s.id}/report`
                      : `/projects/${projectId}/sessions/${s.id}`
                  }
                  className="flex justify-between rounded bg-eprep-bg px-3 py-2 hover:bg-eprep-purple/20"
                >
                  <span>
                    {s.mode.replaceAll("_", " ")} · {new Date(s.started_at).toLocaleString()}
                  </span>
                  <span
                    className={
                      s.status === "completed" ? "text-eprep-electric" : "text-eprep-muted"
                    }
                  >
                    {s.status}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

export default function ProjectDashboard() {
  return (
    <RequireAuth>
      <DashboardInner />
    </RequireAuth>
  );
}
