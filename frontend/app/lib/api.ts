const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type RepoSummary = {
  safe_name: string;
  url: string;
  name: string;
  default_branch: string;
  collected_at: string;
  counts: { commits: number; issues: number; pull_requests: number; releases: number };
  contributor_count: number | null;
  event_counts: Record<string, number>;
};

export type EventAuthor = { name: string | null; github_login: string | null; is_bot?: boolean } | null;

export type EventSummary = {
  id: number;
  event_type: string;
  source_pr_number: number | null;
  primary_commit_hash: string | null;
  title: string;
  author: EventAuthor;
  occurred_at: string;
};

export type EventList = { total: number; limit: number; offset: number; events: EventSummary[] };

export type CommitDetail = {
  hash: string;
  author_name: string | null;
  message: string | null;
  author_date_utc: string | null;
  insertions: number | null;
  deletions: number | null;
};

export type EventDetail = EventSummary & {
  granularity: string;
  pr_detail: { body: string | null; state: string; base_branch: string; head_branch: string; merge_commit_sha: string | null } | null;
  commits: CommitDetail[];
};

export type JobLogEntry = { stage: string; at: string; [key: string]: unknown };

export type Job = {
  id: string;
  repo_url: string;
  status: "pending" | "running" | "done" | "error";
  stage: string;
  log: JobLogEntry[];
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listRepositories: () => apiFetch<RepoSummary[]>("/api/repositories"),
  getRepository: (safeName: string) => apiFetch<RepoSummary>(`/api/repositories/${encodeURIComponent(safeName)}`),
  listEvents: (safeName: string, granularity: string, offset: number, limit = 25, eventType?: string | null) => {
    const q = new URLSearchParams({ granularity, limit: String(limit), offset: String(offset) });
    if (eventType) q.set("event_type", eventType);
    return apiFetch<EventList>(`/api/repositories/${encodeURIComponent(safeName)}/events?${q.toString()}`);
  },
  getEvent: (safeName: string, eventId: number) =>
    apiFetch<EventDetail>(`/api/repositories/${encodeURIComponent(safeName)}/events/${eventId}`),
  startPipeline: (repoUrl: string) =>
    apiFetch<{ job_id: string }>("/api/pipeline/run", { method: "POST", body: JSON.stringify({ repo_url: repoUrl }) }),
  getJob: (jobId: string) => apiFetch<Job>(`/api/pipeline/jobs/${jobId}`),
};
