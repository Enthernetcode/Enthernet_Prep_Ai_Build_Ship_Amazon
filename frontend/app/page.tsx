import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col items-center justify-center gap-12 px-6 py-16">
      <header className="text-center">
        <p className="text-sm uppercase tracking-[0.4em] text-eprep-muted">Enthernet</p>
        <h1 className="mt-4 bg-gradient-to-r from-eprep-magenta via-eprep-purple to-eprep-electric bg-clip-text text-6xl font-bold text-transparent md:text-7xl">
          Prep AI
        </h1>
        <p className="mt-6 text-lg text-eprep-muted">Live in the Moment.</p>
      </header>

      <section className="w-full max-w-xl rounded-2xl border border-eprep-purple/30 bg-eprep-surface p-8 shadow-2xl shadow-eprep-purple/10">
        <h2 className="text-2xl font-semibold text-eprep-text">Prepare for the moment that matters.</h2>
        <p className="mt-3 text-eprep-muted">
          Upload your CV and target job description. Enthernet builds your competency map,
          drills you like a real interviewer, and tracks readiness that adapts every turn.
        </p>
        <div className="mt-8 flex flex-wrap gap-4">
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
      </section>
    </main>
  );
}
