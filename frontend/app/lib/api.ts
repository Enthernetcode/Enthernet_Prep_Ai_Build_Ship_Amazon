export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

const TOKEN_KEY = "eprep.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

interface Options {
  method?: string;
  body?: unknown;
  auth?: boolean;
  form?: FormData;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.auth !== false) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    body = JSON.stringify(opts.body);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method ?? (body ? "POST" : "GET"),
    headers,
    body,
  });
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!res.ok) {
    const detail =
      typeof parsed === "object" && parsed && "detail" in parsed
        ? (parsed as { detail: unknown }).detail
        : parsed;
    throw new ApiError(res.status, detail);
  }
  return parsed as T;
}

export interface Project {
  id: string;
  user_id: string;
  name: string;
  goal_type: string;
  goal_description: string | null;
  target_date: string | null;
  difficulty: number;
  evaluation_profile: Record<string, unknown> | null;
  created_at: string;
}

export interface DocumentSummary {
  id: string;
  project_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  error: string | null;
  created_at: string;
}

export interface Competency {
  id: string;
  project_id: string;
  kind: string;
  label: string;
  detail: string | null;
  confidence: number;
  mastery: number;
  attempts: number;
  correct: number;
  source_document_id: string | null;
  source_chunk_ordinal: number | null;
  created_at: string;
  updated_at: string;
}

export interface Readiness {
  id: string;
  project_id: string;
  session_id: string | null;
  source: string;
  overall: number;
  knowledge: number;
  communication: number;
  evidence: number;
  conciseness: number;
  pressure: number;
  consistency: number;
  coverage: number;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface Turn {
  id: string;
  session_id: string;
  ordinal: number;
  question: string;
  topic: string | null;
  difficulty: number;
  competency_id: string | null;
  grounding: Record<string, unknown> | null;
  user_answer: string | null;
  evaluation: {
    overall: number;
    dimensions: Record<string, number>;
  } | null;
  adaptive_action: {
    action: string;
    next_difficulty: number;
    coach_note: string | null;
    should_finish: boolean;
  } | null;
  coach_note: string | null;
  asked_at: string;
  answered_at: string | null;
}

export interface SessionDetail {
  id: string;
  project_id: string;
  mode: string;
  status: string;
  difficulty: number;
  summary: {
    turns_answered?: number;
    turns_total?: number;
    average_turn_score?: number;
    final_readiness?: number;
    final_scores?: Record<string, number>;
    mode?: string;
  } | null;
  started_at: string;
  completed_at: string | null;
  turns: Turn[];
}
