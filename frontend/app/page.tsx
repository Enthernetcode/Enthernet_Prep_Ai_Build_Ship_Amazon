"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, seedDemo, setToken } from "./lib/api";
import { useAuth } from "./lib/auth";

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
  const { isAdmin } = useAuth();
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
    <main className="flex min-h-screen flex-col">
      {/* Top nav bar — brand mark on the left so the site name is always
          visible, auth links on the right. Overlays the hero at the top. */}
      <nav className="absolute inset-x-0 top-0 z-30 flex items-center justify-between px-4 py-4 md:px-8">
        <Link href="/" className="flex items-center gap-3">
          <Image
            src="/enthernet-logo.png"
            alt="Enthernet"
            width={130}
            height={67}
            priority
            className="h-8 w-auto md:h-10"
          />
          <span className="hidden text-sm font-semibold tracking-widest text-eprep-text sm:inline">
            ENTHERNET&nbsp;·&nbsp;PREP AI
          </span>
        </Link>
        <div className="flex items-center gap-2 text-sm">
          <Link
            href="/mcp-tester"
            className="rounded-md border border-eprep-electric/60 px-3 py-1.5 font-medium text-eprep-electric hover:bg-eprep-electric/10"
            title="Browser-only MCP client for the Alexa+ submission surface"
          >
            MCP tester
          </Link>
          {isAdmin && (
            <Link
              href="/admin"
              className="rounded-md px-3 py-1.5 font-medium text-eprep-electric hover:text-eprep-magenta"
            >
              Admin
            </Link>
          )}
          <Link
            href="/login"
            className="rounded-md px-3 py-1.5 font-medium text-eprep-muted hover:text-eprep-text"
          >
            Log in
          </Link>
          <Link
            href="/register"
            className="rounded-md border border-eprep-purple/60 px-3 py-1.5 font-medium text-eprep-text hover:bg-eprep-purple/10"
          >
            Sign up
          </Link>
        </div>
      </nav>

      {/* Hero — background.png as backdrop, dimmed gradient overlay for
          readability, wordmark + action card stacked bottom-center. */}
      <section
        aria-labelledby="hero-heading"
        className="relative flex min-h-[85vh] w-full items-end justify-center overflow-hidden md:min-h-[95vh]"
      >
        {/* Backdrop image, purely decorative. */}
        <div
          aria-hidden
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: "url('/background.png')" }}
        />
        {/* Dark overlays: bottom gradient (guarantees CTA contrast) + a very
            light top vignette for depth. */}
        <div
          aria-hidden
          className="absolute inset-0 bg-gradient-to-t from-eprep-bg via-eprep-bg/70 to-transparent"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-eprep-bg/20"
        />

        <div className="relative z-10 mx-auto flex w-full max-w-xl flex-col items-center gap-6 px-6 pb-12 md:pb-16">
          {/* Visible site name — the image also shows it but this guarantees
              the brand is always present regardless of how the image crops. */}
          <div className="text-center">
            <p className="text-xs uppercase tracking-[0.5em] text-eprep-muted md:text-sm">
              Enthernet
            </p>
            <h1
              id="hero-heading"
              className="mt-2 bg-gradient-to-r from-eprep-magenta via-eprep-purple to-eprep-electric bg-clip-text text-5xl font-bold text-transparent drop-shadow-[0_2px_20px_rgba(122,43,255,0.35)] md:text-7xl"
            >
              Prep AI
            </h1>
            <p className="mt-3 text-base text-eprep-text md:text-lg">
              Live in the Moment.
            </p>
          </div>

          <div className="w-full rounded-2xl border border-eprep-purple/40 bg-eprep-surface/80 p-6 shadow-2xl shadow-eprep-purple/20 backdrop-blur-md md:p-8">
            <p className="text-xs uppercase tracking-[0.35em] text-eprep-muted">
              Prepare for the moment that matters
            </p>
            <p className="mt-3 text-eprep-text">
              Bring your CV, notes, documents or pitch. Enthernet builds your
              competency map, challenges you in realistic simulations, and measures
              readiness as you improve.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                onClick={runSeed}
                disabled={seeding}
                className="rounded-lg bg-eprep-magenta px-5 py-2.5 font-medium text-white shadow-lg shadow-eprep-magenta/30 transition hover:bg-eprep-purple disabled:opacity-60"
              >
                {seeding ? "Preparing demo…" : "Try the 60-second demo"}
              </button>
              <Link
                href="/login"
                className="rounded-lg bg-eprep-purple px-5 py-2.5 font-medium text-white hover:bg-eprep-magenta"
              >
                Log in
              </Link>
              <Link
                href="/register"
                className="rounded-lg border border-eprep-purple px-5 py-2.5 font-medium text-eprep-text hover:bg-eprep-purple/10"
              >
                Create account
              </Link>
            </div>
            {seedError && (
              <p className="mt-4 text-sm text-eprep-magenta">{seedError}</p>
            )}
          </div>
        </div>
      </section>

      {/* Steps + footer — full-width container, content centered. */}
      <div className="mx-auto flex w-full max-w-4xl flex-col items-center gap-16 px-6 py-20">
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
      </div>
    </main>
  );
}
