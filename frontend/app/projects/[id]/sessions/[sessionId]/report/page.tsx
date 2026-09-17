"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { RequireAuth } from "../../../../../lib/auth";
import { api, ApiError, Readiness, SessionDetail } from "../../../../../lib/api";

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

function ReportInner() {
  const params = useParams<{ id: string; sessionId: string }>();
  const projectId = params.id;
  const sessionId = params.sessionId;

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const s = await api<SessionDetail>(`/sessions/${sessionId}`);
        setSession(s);
        try {
          setReadiness(await api<Readiness>(`/projects/${projectId}/readiness/`));
        } catch (e) {
          if (!(e instanceof ApiError) || e.status !== 404) throw e;
        }
      } catch (err) {
        setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed");
      }
    })();
  }, [projectId, sessionId]);

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center text-eprep-muted">
        {error ? <span className="text-eprep-magenta">{error}</span> : "Loading…"}
      </div>
    );
  }

  const scores =
    readiness ??
    (session.summary?.final_scores
      ? ({
          overall: session.summary.final_readiness ?? 0,
          knowledge: session.summary.final_scores.knowledge,
          communication: session.summary.final_scores.communication,
          evidence: session.summary.final_scores.evidence,
          conciseness: session.summary.final_scores.conciseness,
          pressure: session.summary.final_scores.pressure,
          consistency: session.summary.final_scores.consistency,
          coverage: session.summary.final_scores.coverage,
        } as Readiness)
      : null);

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <nav className="mb-6 text-sm text-eprep-muted">
        <Link href={`/projects/${projectId}`} className="hover:text-eprep-electric">
          ← Dashboard
        </Link>
      </nav>

      <header className="mb-8 text-center">
        <p className="text-xs uppercase tracking-[0.35em] text-eprep-muted">
          Enthernet Prep AI
        </p>
        <h1 className="mt-2 text-3xl font-semibold">
          {session.mode === "final_boss" ? "Final Readiness Report" : "Session Report"}
        </h1>
      </header>

      {scores && (
        <>
          <section className="mx-auto mb-8 max-w-md rounded-2xl border border-eprep-electric/50 bg-eprep-surface p-8 text-center">
            <p className="text-xs uppercase tracking-widest text-eprep-muted">
              Overall readiness
            </p>
            <p className="mt-2 text-6xl font-bold text-eprep-electric">
              {pct(scores.overall)}
            </p>
            <p className="mt-2 text-sm text-eprep-muted">
              Status:{" "}
              <span className="font-medium text-eprep-text">
                {scores.overall >= 0.85
                  ? "READY"
                  : scores.overall >= 0.65
                    ? "ON TRACK"
                    : "NEEDS WORK"}
              </span>
            </p>
          </section>

          <section className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
            {(
              [
                ["Knowledge", scores.knowledge],
                ["Communication", scores.communication],
                ["Evidence", scores.evidence],
                ["Conciseness", scores.conciseness],
                ["Pressure", scores.pressure],
                ["Consistency", scores.consistency],
                ["Coverage", scores.coverage],
              ] as const
            ).map(([label, value]) => (
              <div
                key={label}
                className="rounded-xl border border-eprep-purple/30 bg-eprep-surface p-4 text-center"
              >
                <p className="text-xs uppercase text-eprep-muted">{label}</p>
                <p className="mt-1 text-2xl font-semibold">{pct(value)}</p>
              </div>
            ))}
          </section>
        </>
      )}

      <section className="rounded-xl border border-eprep-purple/30 bg-eprep-surface p-6">
        <h2 className="mb-4 text-lg font-medium">Turn breakdown</h2>
        <ol className="space-y-4 text-sm">
          {session.turns.map((t) => (
            <li key={t.id} className="rounded bg-eprep-bg p-4">
              <p className="text-xs text-eprep-muted">
                #{t.ordinal} · {t.topic} · difficulty {t.difficulty}
              </p>
              <p className="mt-1">{t.question}</p>
              {t.user_answer && (
                <p className="mt-2 whitespace-pre-wrap text-eprep-muted">{t.user_answer}</p>
              )}
              {t.evaluation && (
                <p className="mt-2 text-xs text-eprep-electric">
                  Score {pct(t.evaluation.overall)} ·{" "}
                  {Object.entries(t.evaluation.dimensions)
                    .slice(0, 4)
                    .map(([k, v]) => `${k} ${pct(v)}`)
                    .join(" · ")}
                </p>
              )}
              {t.coach_note && (
                <p className="mt-2 text-xs italic text-eprep-muted">💡 {t.coach_note}</p>
              )}
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}

export default function ReportPage() {
  return (
    <RequireAuth>
      <ReportInner />
    </RequireAuth>
  );
}
