"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "../lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setError(null);
    setSubmitting(true);
    try {
      const resp = await api<{ detail: string }>("/auth/forgot-password", {
        body: { email },
        auth: false,
      });
      setMessage(resp.detail);
    } catch (err) {
      // 503 means SMTP isn't configured yet — surface that honestly to the
      // user so they know to contact the admin.
      if (err instanceof ApiError && err.status === 503) {
        setError(
          "Password reset isn't available yet — the administrator hasn't configured outbound email.",
        );
      } else {
        setError(
          err instanceof ApiError
            ? String(err.detail ?? err.message)
            : "Something went wrong.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
      <h1 className="mb-2 text-3xl font-semibold">Forgot your password?</h1>
      <p className="mb-8 text-sm text-eprep-muted">
        Enter the email you registered with. We'll send you a reset link that
        works for 30 minutes.
      </p>
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
        {error && <p className="text-sm text-eprep-magenta">{error}</p>}
        {message && (
          <p className="rounded-md border border-eprep-electric/40 bg-eprep-electric/10 px-3 py-2 text-sm text-eprep-electric">
            {message}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-60"
        >
          {submitting ? "Sending…" : "Send reset link"}
        </button>
      </form>
      <p className="mt-6 text-sm text-eprep-muted">
        Remembered it?{" "}
        <Link href="/login" className="text-eprep-electric hover:underline">
          Back to log in
        </Link>
      </p>
    </main>
  );
}
