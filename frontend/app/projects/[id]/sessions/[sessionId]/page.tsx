"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { RequireAuth } from "../../../../lib/auth";
import {
  api,
  ApiError,
  Readiness,
  SessionDetail,
  Turn,
} from "../../../../lib/api";

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

function SessionInner() {
  const params = useParams<{ id: string; sessionId: string }>();
  const router = useRouter();
  const projectId = params.id;
  const sessionId = params.sessionId;

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const startedAtRef = useRef<number | null>(null);

  const activeTurn: Turn | undefined = useMemo(
    () => session?.turns.find((t) => t.user_answer === null),
    [session],
  );
  const lastAnswered: Turn | undefined = useMemo(() => {
    if (!session) return undefined;
    const answered = session.turns.filter((t) => t.user_answer !== null);
    return answered[answered.length - 1];
  }, [session]);

  const loadSession = useCallback(async () => {
    const s = await api<SessionDetail>(`/sessions/${sessionId}`);
    setSession(s);
    return s;
  }, [sessionId]);

  const loadReadiness = useCallback(async () => {
    try {
      setReadiness(await api<Readiness>(`/projects/${projectId}/readiness/`));
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 404) throw e;
    }
  }, [projectId]);

  useEffect(() => {
    (async () => {
      try {
        const s = await loadSession();
        await loadReadiness();
        if (s.status === "active" && !s.turns.some((t) => t.user_answer === null)) {
          await requestQuestion();
        }
      } catch (err) {
        setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed");
      }
    })();
  }, [loadSession, loadReadiness]);

  useEffect(() => {
    if (activeTurn) startedAtRef.current = Date.now();
  }, [activeTurn?.id]);

  const requestQuestion = async () => {
    setBusy(true);
    setError(null);
    try {
      await api<Turn>(`/sessions/${sessionId}/turns`, { method: "POST" });
      await loadSession();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!activeTurn || !answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const seconds = startedAtRef.current
        ? (Date.now() - startedAtRef.current) / 1000
        : null;
      await api<Turn>(`/sessions/${sessionId}/turns/${activeTurn.ordinal}/answer`, {
        body: { answer, seconds_taken: seconds },
      });
      setAnswer("");
      const refreshed = await loadSession();
      await loadReadiness();
      // If the planner said finish, refetch will show status; else fetch next question.
      const stillActive = refreshed.status === "active";
      const noPending = !refreshed.turns.some((t) => t.user_answer === null);
      if (stillActive && noPending) {
        const last = refreshed.turns[refreshed.turns.length - 1];
        if (last?.adaptive_action?.should_finish) {
          await finish();
        } else {
          await requestQuestion();
        }
      }
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    try {
      await api(`/sessions/${sessionId}/finish`, { method: "POST" });
      router.push(`/projects/${projectId}/sessions/${sessionId}/report`);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed");
    } finally {
      setBusy(false);
    }
  };

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center text-eprep-muted">
        {error ? <span className="text-eprep-magenta">{error}</span> : "Loading…"}
      </div>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <nav className="mb-6 flex items-center justify-between text-sm text-eprep-muted">
        <Link href={`/projects/${projectId}`} className="hover:text-eprep-electric">
          ← Dashboard
        </Link>
        <span>
          {session.mode.replaceAll("_", " ")} · difficulty {session.difficulty}
        </span>
      </nav>

      {readiness && (
        <div className="mb-6 flex items-center justify-between rounded-lg border border-eprep-electric/30 bg-eprep-surface px-5 py-3">
          <span className="text-sm text-eprep-muted">Live readiness</span>
          <span className="text-2xl font-semibold text-eprep-electric">
            {pct(readiness.overall)}
          </span>
        </div>
      )}

      {activeTurn ? (
        <section className="rounded-xl border border-eprep-purple/40 bg-eprep-surface p-6">
          <p className="text-xs uppercase tracking-widest text-eprep-muted">
            Question {activeTurn.ordinal} · difficulty {activeTurn.difficulty} ·{" "}
            {activeTurn.topic}
          </p>
          <h2 className="mt-3 text-xl leading-relaxed">{activeTurn.question}</h2>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Type your answer…"
              rows={7}
              required
              className="w-full rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2 focus:border-eprep-electric focus:outline-none"
            />
            <div className="flex justify-between">
              <button
                type="button"
                onClick={finish}
                disabled={busy}
                className="text-sm text-eprep-muted hover:text-eprep-magenta"
              >
                Finish early
              </button>
              <button
                type="submit"
                disabled={busy || !answer.trim()}
                className="rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-40"
              >
                {busy ? "Working…" : "Submit answer"}
              </button>
            </div>
          </form>
        </section>
      ) : session.status === "completed" ? (
        <section className="rounded-xl border border-eprep-electric/40 bg-eprep-surface p-6 text-center">
          <p className="text-lg">Session complete.</p>
          <Link
            href={`/projects/${projectId}/sessions/${sessionId}/report`}
            className="mt-4 inline-block rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta"
          >
            View report
          </Link>
        </section>
      ) : (
        <p className="text-eprep-muted">Preparing next question…</p>
      )}

      {error && <p className="mt-4 text-sm text-eprep-magenta">{error}</p>}

      {lastAnswered?.evaluation && (
        <section className="mt-8 rounded-xl border border-eprep-purple/20 bg-eprep-surface p-6">
          <p className="text-xs uppercase tracking-widest text-eprep-muted">
            Last answer feedback
          </p>
          <p className="mt-2 text-sm">Score: {pct(lastAnswered.evaluation.overall)}</p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
            {Object.entries(lastAnswered.evaluation.dimensions).map(([k, v]) => (
              <div key={k} className="rounded bg-eprep-bg px-2 py-1">
                <span className="text-eprep-muted">{k}</span>: {pct(v)}
              </div>
            ))}
          </div>
          {lastAnswered.coach_note && (
            <p className="mt-3 text-sm text-eprep-electric">💡 {lastAnswered.coach_note}</p>
          )}
          {lastAnswered.adaptive_action && (
            <p className="mt-2 text-xs text-eprep-muted">
              Planner: {lastAnswered.adaptive_action.action.replaceAll("_", " ")} → next
              difficulty {lastAnswered.adaptive_action.next_difficulty}
            </p>
          )}
        </section>
      )}

      {session.turns.length > 1 && (
        <details className="mt-8 rounded-xl border border-eprep-purple/20 bg-eprep-surface p-6">
          <summary className="cursor-pointer text-sm text-eprep-muted">
            Turn history ({session.turns.length})
          </summary>
          <ol className="mt-4 space-y-3 text-sm">
            {session.turns.map((t) => (
              <li key={t.id} className="rounded bg-eprep-bg p-3">
                <p className="text-xs text-eprep-muted">
                  #{t.ordinal} · {t.topic} · difficulty {t.difficulty}
                </p>
                <p className="mt-1">{t.question}</p>
                {t.user_answer && (
                  <p className="mt-2 whitespace-pre-wrap text-eprep-muted">{t.user_answer}</p>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
    </main>
  );
}

export default function SessionPage() {
  return (
    <RequireAuth>
      <SessionInner />
    </RequireAuth>
  );
}
