"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? String(err.detail ?? err.message)
          : "Login failed",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
      <h1 className="mb-8 text-3xl font-semibold">Log in</h1>
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block">
          <span className="text-xs uppercase tracking-widest text-eprep-muted">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-eprep-purple/40 bg-eprep-surface px-3 py-2 focus:border-eprep-electric focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-widest text-eprep-muted">Password</span>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-eprep-purple/40 bg-eprep-surface px-3 py-2 focus:border-eprep-electric focus:outline-none"
          />
        </label>
        {error && <p className="text-sm text-eprep-magenta">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-60"
        >
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>
      <p className="mt-6 text-sm text-eprep-muted">
        No account?{" "}
        <Link href="/register" className="text-eprep-electric hover:underline">
          Register
        </Link>
      </p>
      <p className="mt-2 text-sm text-eprep-muted">
        Forgot your password?{" "}
        <Link
          href="/forgot-password"
          className="text-eprep-electric hover:underline"
        >
          Reset it
        </Link>
      </p>
    </main>
  );
}
