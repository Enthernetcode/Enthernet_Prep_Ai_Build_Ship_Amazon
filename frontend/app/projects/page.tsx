"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RequireAuth, useAuth } from "../lib/auth";
import { api, ApiError, Project } from "../lib/api";

function ProjectsInner() {
  const { logout } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [goalType, setGoalType] = useState("job_interview");
  const [targetDate, setTargetDate] = useState("");
  const [difficulty, setDifficulty] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setProjects(await api<Project[]>("/projects/"));
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      await api<Project>("/projects/", {
        body: {
          name,
          goal_type: goalType,
          target_date: targetDate || null,
          difficulty,
        },
      });
      setName("");
      setTargetDate("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed");
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Your preparation projects</h1>
        <button onClick={logout} className="text-sm text-eprep-muted hover:text-eprep-magenta">
          Log out
        </button>
      </header>

      <section className="mb-10 rounded-xl border border-eprep-purple/30 bg-eprep-surface p-6">
        <h2 className="mb-4 text-lg font-medium">New project</h2>
        <form onSubmit={create} className="grid gap-3 md:grid-cols-4">
          <input
            required
            placeholder="Project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2 md:col-span-2"
          />
          <select
            value={goalType}
            onChange={(e) => setGoalType(e.target.value)}
            className="rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2"
          >
            <option value="job_interview">Job interview</option>
            <option value="pitch">Pitch</option>
            <option value="exam">Exam</option>
          </select>
          <input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            className="rounded-md border border-eprep-purple/40 bg-eprep-bg px-3 py-2"
          />
          <label className="text-sm text-eprep-muted md:col-span-3">
            Difficulty {difficulty}
            <input
              type="range"
              min={1}
              max={6}
              value={difficulty}
              onChange={(e) => setDifficulty(Number(e.target.value))}
              className="ml-3 align-middle"
            />
          </label>
          <button
            disabled={creating}
            className="rounded-md bg-eprep-purple px-4 py-2 font-medium text-white hover:bg-eprep-magenta disabled:opacity-60"
          >
            {creating ? "Creating…" : "Create"}
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-eprep-magenta">{error}</p>}
      </section>

      <section>
        {loading ? (
          <p className="text-eprep-muted">Loading…</p>
        ) : projects.length === 0 ? (
          <p className="text-eprep-muted">No projects yet. Create one above.</p>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {projects.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/projects/${p.id}`}
                  className="block rounded-xl border border-eprep-purple/30 bg-eprep-surface p-5 transition hover:border-eprep-electric"
                >
                  <p className="text-xs uppercase tracking-widest text-eprep-muted">
                    {p.goal_type.replaceAll("_", " ")}
                  </p>
                  <p className="mt-1 text-lg font-medium">{p.name}</p>
                  <p className="mt-2 text-xs text-eprep-muted">
                    Target: {p.target_date ?? "unspecified"} · difficulty {p.difficulty}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

export default function ProjectsPage() {
  return (
    <RequireAuth>
      <ProjectsInner />
    </RequireAuth>
  );
}
