"use client";

import { useEffect, useState } from "react";
import { api, ApiError, Announcement } from "../lib/api";
import { useAuth } from "../lib/auth";

const KIND_STYLES: Record<Announcement["kind"], string> = {
  info: "border-eprep-electric/50 bg-eprep-electric/10 text-eprep-electric",
  warning: "border-yellow-400/50 bg-yellow-400/10 text-yellow-300",
  success: "border-emerald-400/50 bg-emerald-400/10 text-emerald-300",
};

const DISMISSED_KEY = "eprep.dismissedAnnouncements";

function loadDismissed(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    return new Set(JSON.parse(window.localStorage.getItem(DISMISSED_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}

function saveDismissed(set: Set<string>): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(DISMISSED_KEY, JSON.stringify(Array.from(set)));
}

export function AnnouncementBanner() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState<Announcement[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  useEffect(() => {
    setDismissed(loadDismissed());
  }, []);

  useEffect(() => {
    if (loading || !user) return;
    (async () => {
      try {
        setItems(await api<Announcement[]>("/announcements/"));
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 401) {
          console.warn("announcements fetch failed", err);
        }
      }
    })();
  }, [loading, user]);

  const visible = items.filter((a) => !dismissed.has(a.id));
  if (visible.length === 0) return null;

  const dismiss = (id: string) => {
    const next = new Set(dismissed);
    next.add(id);
    setDismissed(next);
    saveDismissed(next);
  };

  return (
    <div className="sticky top-0 z-40 flex flex-col gap-1 px-3 pt-2">
      {visible.map((a) => (
        <div
          key={a.id}
          className={`flex items-start justify-between gap-3 rounded-md border px-4 py-2 text-sm shadow-md ${KIND_STYLES[a.kind]}`}
          role="status"
        >
          <div>
            <p className="font-semibold">{a.title}</p>
            <p className="text-xs opacity-80">{a.body}</p>
          </div>
          <button
            onClick={() => dismiss(a.id)}
            className="text-xs opacity-70 hover:opacity-100"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
