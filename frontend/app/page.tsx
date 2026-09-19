"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, seedDemo, setToken } from "./lib/api";

const STEPS = [
  {
    title: "Bring your material",
    body:
      "Upload the documents that describe what you're preparing for — a CV, " +
      "a job description, a pitch deck, notes, or a research brief. PDF, " +
      "DOCX, TXT and Markdown all work.",
  },
  {
    title: "See your competency map",
    body:
      "Enthernet reads what you uploaded and extracts the concrete skills, " +
      "technologies, claims and metrics into a personal competency map — the " +
      "vocabulary the rest of the system will drill against.",
  },
  {
    title: "Set a baseline readiness",
    body:
      "Before you practice, Enthernet gives you a deterministic baseline: " +
      "modest by design, because readiness is proven through performance, " +
      "not implied by documents.",
  },
  {
    title: "Practice in adaptive simulations",
    body:
      "Answer grounded questions on the web with your keyboard or your mic, " +
      "or over voice through Alexa+ (MCP). A seven-dimension rubric scores " +
      "every answer; the planner raises the difficulty when you're strong, " +
      "slows down and coaches when you're not.",
  },
  {
    title: "Face the Final Boss",
    body:
      "When you're ready, run the graded assessment — hints off, adaptive " +
      "difficulty on, contradiction detection on. You leave with a Readiness " +
      "Report you can act on.",
  },
];

export default function HomePage() {
  const router = useRouter();
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);

  const runSeed = async () => {
    setSeedError(null);
    setSeeding(true);
    try {
      const res = await seedDemo();
      setToken(res.access_token);
      router.push(res.dashboard_path);
    } catch (err) {
      setSeedError(
        err instanceof ApiError
          ? String(err.detail ?? err.message)
          : "Demo unavailable",
      );
      setSeeding(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col items-center gap-16 px-6 py-16">
      <header className="text-center">
        <p className="text-sm uppercase tracking-[0.4em] text-eprep-muted">Enthernet</p>
        <h1 className="mt-4 bg-gradient-to-r from-eprep-magenta via-eprep-purple to-eprep-electric bg-clip-text text-6xl font-bold text-transparent md:text-7xl">
          Prep AI
        </h1>
        <p className="mt-6 text-lg text-eprep-muted">Live in the Moment.</p>
      </header>

      <section
        aria-labelledby="hero-heading"
        className="w-full max-w-xl rounded-2xl border border-eprep-purple/30 bg-eprep-surface p-8 shadow-2xl shadow-eprep-purple/10"
      >
        <h2 id="hero-heading" className="text-2xl font-semibold text-eprep-text">
          Prepare for the moment that matters.
        </h2>
        <p className="mt-3 text-eprep-muted">
          Bring your CV, notes, documents or pitch. Enthernet builds your competency map,
          challenges you in realistic simulations, and measures readiness as you improve.
        </p>
        <div className="mt-8 flex flex-wrap gap-4">
          <button
            onClick={runSeed}
            disabled={seeding}
            className="rounded-lg bg-eprep-magenta px-6 py-3 font-medium text-white shadow-lg shadow-eprep-magenta/30 transition hover:bg-eprep-purple disabled:opacity-60"
          >
            {seeding ? "Preparing demo…" : "Try the 60-second demo"}
          </button>
          <Link
            href="/login"
            className="rounded-lg bg-eprep-purple px-6 py-3 font-medium text-white hover:bg-eprep-magenta"
          >
            Log in
          </Link>
          <Link
            href="/register"
            className="rounded-lg border border-eprep-purple px-6 py-3 font-medium text-eprep-text hover:bg-eprep-purple/10"
          >
            Create account
          </Link>
        </div>
        {seedError && (
          <p className="mt-4 text-sm text-eprep-magenta">{seedError}</p>
        )}
      </section>

      <section aria-labelledby="how-heading" className="w-full max-w-3xl">
        <div className="mb-8 text-center">
          <p className="text-xs uppercase tracking-[0.35em] text-eprep-muted">
            How Enthernet Prep AI works
          </p>
          <h2
            id="how-heading"
            className="mt-3 text-3xl font-semibold text-eprep-text md:text-4xl"
          >
            Five steps from documents to readiness.
          </h2>
        </div>
        <ol className="grid gap-4 md:grid-cols-2">
          {STEPS.map((step, i) => (
            <li
              key={step.title}
              className="rounded-xl border border-eprep-purple/25 bg-eprep-surface p-6 transition hover:border-eprep-electric/60"
            >
              <div className="flex items-baseline gap-3">
                <span className="bg-gradient-to-br from-eprep-magenta to-eprep-electric bg-clip-text text-4xl font-bold leading-none text-transparent">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="text-lg font-semibold text-eprep-text">
                  {step.title}
                </h3>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-eprep-muted">
                {step.body}
              </p>
            </li>
          ))}
        </ol>
        <p className="mt-8 text-center text-sm text-eprep-muted">
          Two interfaces, one engine —{" "}
          <span className="text-eprep-text">web</span> for structured practice,{" "}
          <span className="text-eprep-text">Alexa+</span> via Model Context
          Protocol for hands-free voice.
        </p>
      </section>

      <footer className="mt-4 text-center text-xs text-eprep-muted">
        <p>
          Built by <span className="text-eprep-text">Enthernet</span>. Live in the Moment.
        </p>
      </footer>
    </main>
  );
}
