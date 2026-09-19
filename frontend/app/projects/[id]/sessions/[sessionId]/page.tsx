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

// Vendor-prefixed types for the Web Speech API — kept minimal so we don't
// pull in a heavyweight typings package.
interface SpeechRecognitionEventLike {
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      [index: number]: { transcript: string };
    };
  };
  resultIndex: number;
}
interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;
declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

const TTS_KEY = "eprep.tts";

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
  const [interim, setInterim] = useState("");
  const [listening, setListening] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const startedAtRef = useRef<number | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const spokenIdRef = useRef<string | null>(null);

  const sttSupported =
    typeof window !== "undefined" &&
    !!(window.SpeechRecognition ?? window.webkitSpeechRecognition);
  const ttsSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

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

  // Restore TTS preference.
  useEffect(() => {
    if (typeof window === "undefined") return;
    setTtsEnabled(window.localStorage.getItem(TTS_KEY) === "1");
  }, []);

  // Speak each new question exactly once when TTS is on.
  useEffect(() => {
    if (!ttsEnabled || !ttsSupported || !activeTurn) return;
    if (spokenIdRef.current === activeTurn.id) return;
    spokenIdRef.current = activeTurn.id;
    const utterance = new SpeechSynthesisUtterance(activeTurn.question);
    utterance.rate = 1.0;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  }, [ttsEnabled, ttsSupported, activeTurn?.id, activeTurn?.question]);

  // Stop any in-flight speech when the component unmounts.
  useEffect(() => {
    return () => {
      if (ttsSupported) window.speechSynthesis.cancel();
      recognitionRef.current?.stop();
    };
  }, [ttsSupported]);

  const toggleTts = () => {
    const next = !ttsEnabled;
    setTtsEnabled(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TTS_KEY, next ? "1" : "0");
      if (!next) window.speechSynthesis.cancel();
    }
  };

  const startListening = () => {
    if (!sttSupported) return;
    const Ctor =
      window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Ctor) return;
    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      let finalDelta = "";
      let interimDelta = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = result[0].transcript;
        if (result.isFinal) finalDelta += transcript;
        else interimDelta += transcript;
      }
      if (finalDelta) {
        setAnswer((prev) => (prev ? prev + " " + finalDelta : finalDelta).trim());
      }
      setInterim(interimDelta);
    };
    recognition.onerror = (event) => {
      setError(`Voice input: ${event.error ?? "unknown error"}`);
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
      setInterim("");
    };
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
    setError(null);
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setListening(false);
  };

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
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-widest text-eprep-muted">
                Question {activeTurn.ordinal} · difficulty {activeTurn.difficulty} ·{" "}
                {activeTurn.topic}
              </p>
              <h2 className="mt-3 text-xl leading-relaxed">{activeTurn.question}</h2>
            </div>
            {ttsSupported && (
              <button
                type="button"
                onClick={toggleTts}
                className={`shrink-0 rounded-md border px-3 py-1 text-xs uppercase tracking-widest transition ${
                  ttsEnabled
                    ? "border-eprep-electric text-eprep-electric"
                    : "border-eprep-purple/40 text-eprep-muted hover:text-eprep-text"
                }`}
                title="Read the question aloud"
              >
                {ttsEnabled ? "🔊 On" : "🔈 Off"}
              </button>
            )}
          </div>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div className="relative">
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder={
                  listening
                    ? "Listening… speak your answer"
                    : "Type your answer, or tap the mic to speak…"
                }
                rows={7}
                required
                className={`w-full rounded-md border bg-eprep-bg px-3 py-2 pr-14 focus:outline-none ${
                  listening
                    ? "border-eprep-magenta shadow-[0_0_0_2px_rgba(255,43,214,0.25)]"
                    : "border-eprep-purple/40 focus:border-eprep-electric"
                }`}
              />
              {interim && (
                <p className="mt-1 text-xs italic text-eprep-muted">…{interim}</p>
              )}
              {sttSupported && (
                <button
                  type="button"
                  onClick={listening ? stopListening : startListening}
                  className={`absolute right-2 top-2 rounded-full px-3 py-2 text-sm transition ${
                    listening
                      ? "bg-eprep-magenta text-white animate-pulse"
                      : "bg-eprep-purple/20 text-eprep-electric hover:bg-eprep-purple/40"
                  }`}
                  title={listening ? "Stop listening" : "Start voice input"}
                  aria-label={listening ? "Stop listening" : "Start voice input"}
                >
                  {listening ? "■" : "🎙"}
                </button>
              )}
            </div>
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
