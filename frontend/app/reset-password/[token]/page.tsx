"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "../../lib/api";

export default function ResetPasswordPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setSubmitting(true);
    try {
      await api<{ status: string }>("/auth/reset-password", {
        body: { token, password },
        auth: false,
      });
      setDone(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? String(err.detail ?? err.message)
          : "Something went wrong.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16 text-center">
        <h1 className="mb-3 text-3xl font-semibold text-eprep-electric">
          Password reset.
        </h1>
        <p className="text-sm text-eprep-muted">
          Redirecting you to log in…
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
      <h1 className="mb-2 text-3xl font-semibold">Choose a new password</h1>
      <p className="mb-8 text-sm text-eprep-muted">
        After you save, you'll sign in with the new password.
      </p>
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block">
          <span className="text-xs uppercase tracking-widest text-eprep-muted">
            New password
          </span>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-eprep-purple/40 bg-eprep-surface px-3 py-2 focus:border-eprep-electric focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-widest text-eprep-muted">
            Confirm new password
          </span>
          <input
            type="password"
            required
            minLength={8}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="mt-1 w-full rounded-md border border-eprep-purple/40 bg-eprep-surface px-3 py-2 focus:border-eprep-electric focus:outline-none"
          />
        </label>
        {error && <p className="text-sm text-eprep-magenta">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-60"
        >
          {submitting ? "Saving…" : "Save password"}
        </button>
      </form>
      <p className="mt-6 text-sm text-eprep-muted">
        <Link href="/login" className="text-eprep-electric hover:underline">
          Back to log in
        </Link>
      </p>
    </main>
  );
}
