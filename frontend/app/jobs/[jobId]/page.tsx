"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { BackLink, Panel, SectionLabel, Shell } from "../../components/ui";
import { api, Job } from "../../lib/api";

const STAGES = [
  { key: "cloning", label: "Clone repository", detail: "Mirroring git history locally" },
  { key: "collecting", label: "Collect evidence", detail: "Commits, issues, pull requests, releases" },
  { key: "normalizing", label: "Normalize", detail: "Identities, reverts, file renames" },
  { key: "forming_events", label: "Form events", detail: "PR-bundle and commit-level granularities" },
];

const STAGE_LABELS: Record<string, string> = {
  pending: "Waiting to start",
  starting: "Starting",
  cloning: "Cloning repository",
  collecting: "Collecting evidence",
  collected: "Collected",
  normalizing: "Normalizing",
  normalized: "Normalized",
  forming_events: "Forming candidate events",
  done: "Complete",
};

export default function JobPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      api
        .getJob(jobId)
        .then((j) => {
          if (cancelled) return;
          setJob(j);
          if (j.status === "running" || j.status === "pending") setTimeout(poll, 1500);
        })
        .catch((err) => !cancelled && setError(String(err)));
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const safeName = job?.result ? (job.result.owner_repo as string)?.replace("/", "__") : null;
  const reachedStages = new Set(job?.log.map((l) => l.stage) ?? []);
  const isDone = job?.status === "done";

  return (
    <Shell width="max-w-2xl">
      <BackLink href="/">All repositories</BackLink>

      <h1 className="mt-3 text-xl font-semibold tracking-tight break-all">{job?.repo_url ?? "Loading…"}</h1>
      {job && (
        <p className="mt-1 text-sm text-fg-dim">
          {job.status === "error" ? "Failed" : STAGE_LABELS[job.stage] ?? job.stage}
        </p>
      )}

      {error && <Panel className="mt-6 px-4 py-3 text-sm text-red">{error}</Panel>}

      {job?.status === "error" && (
        <Panel className="mt-6 border-red/25 bg-red/[0.06] px-4 py-3">
          <p className="text-xs uppercase tracking-[0.12em] text-red mb-1.5">Pipeline error</p>
          <p className="font-mono text-xs leading-relaxed text-fg-dim break-all">{job.error}</p>
        </Panel>
      )}

      {isDone && safeName && (
        <Panel className="mt-6 border-cyan-deep/30 bg-cyan-deep/[0.06] px-5 py-4 rise">
          <p className="text-sm text-fg">Collection complete.</p>
          <Link href={`/repos/${safeName}`} className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-cyan hover:underline">
            View repository <span aria-hidden="true">→</span>
          </Link>
        </Panel>
      )}

      {job && (
        <div className="mt-8">
          <SectionLabel>Pipeline</SectionLabel>
          <ol className="relative space-y-0">
            {STAGES.map((stage, i) => {
              const reached = reachedStages.has(stage.key) || isDone;
              const active = !isDone && job.stage === stage.key;
              return (
                <li key={stage.key} className="relative flex gap-4 pb-6 last:pb-0">
                  {i < STAGES.length - 1 && (
                    <span
                      className={`absolute left-[7px] top-5 h-full w-px ${reached ? "bg-cyan-deep/40" : "bg-line"}`}
                      aria-hidden="true"
                    />
                  )}
                  <span
                    className={`relative z-10 mt-1 h-[15px] w-[15px] shrink-0 rounded-full border-2 ${
                      active
                        ? "border-cyan bg-cyan pulse-ring"
                        : reached
                          ? "border-cyan-deep bg-cyan-deep"
                          : "border-line bg-ink-800"
                    }`}
                  />
                  <div className="-mt-0.5">
                    <div className={`text-sm ${reached || active ? "text-fg" : "text-fg-faint"}`}>{stage.label}</div>
                    <div className="text-[11px] text-fg-faint">{stage.detail}</div>
                  </div>
                </li>
              );
            })}
          </ol>

          {job.log.length > 0 && (
            <div className="mt-8">
              <SectionLabel>Log</SectionLabel>
              <Panel className="px-4 py-3">
                <ul className="space-y-1 font-mono text-[11px] leading-relaxed">
                  {job.log.map((entry, i) => (
                    <li key={i} className="flex gap-3">
                      <span className="shrink-0 text-fg-faint">{new Date(entry.at as string).toLocaleTimeString()}</span>
                      <span className="text-fg-dim">
                        {STAGE_LABELS[entry.stage] ?? entry.stage}
                        {"entity" in entry && "count" in entry && (
                          <span className="text-cyan"> · {String(entry.count)} {String(entry.entity)}</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}
