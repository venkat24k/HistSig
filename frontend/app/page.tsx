"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import EventGraph from "./components/EventGraph";
import { Badge, Button, Panel, SectionLabel } from "./components/ui";
import { api, RepoSummary } from "./lib/api";

function IconEvidence() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4.5 w-4.5" strokeWidth="1.6" stroke="currentColor">
      <path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" strokeLinejoin="round" />
      <path d="M14 3v4a1 1 0 0 0 1 1h4" strokeLinejoin="round" />
      <path d="M8.5 13h7M8.5 16.5h5" strokeLinecap="round" />
    </svg>
  );
}

function IconScale() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4.5 w-4.5" strokeWidth="1.6" stroke="currentColor">
      <path d="M12 3v18M7 8H2l2.5 5L2 8Zm15 0h-5l2.5 5L22 8Z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4.5 13a2.5 2.5 0 0 0 5 0M14.5 13a2.5 2.5 0 0 0 5 0" strokeLinecap="round" />
      <path d="M8 21h8" strokeLinecap="round" />
    </svg>
  );
}

function IconBranch() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4.5 w-4.5" strokeWidth="1.6" stroke="currentColor">
      <circle cx="6" cy="5" r="2" />
      <circle cx="6" cy="19" r="2" />
      <circle cx="18" cy="12" r="2" />
      <path d="M6 7v10M6 12h6a4 4 0 0 0 4-4V7" strokeLinecap="round" />
    </svg>
  );
}

const TRUST_ITEMS = [
  { Icon: IconEvidence, title: "Evidence-first mining", body: "Every ranking traces back to real commits, reviews, and comments — nothing invented." },
  { Icon: IconScale, title: "P vs. R, kept separate", body: "Perceived attention and lasting impact are scored independently, never collapsed into one number." },
  { Icon: IconBranch, title: "Two event granularities", body: "Compare PR-bundled history against every commit individually, side by side." },
];

export default function HomePage() {
  const [repos, setRepos] = useState<RepoSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const load = () => {
    api
      .listRepositories()
      .then(setRepos)
      .catch((err) => setError(String(err)));
  };

  useEffect(load, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      const { job_id } = await api.startPipeline(repoUrl.trim());
      window.location.href = `/jobs/${job_id}`;
    } catch (err) {
      setSubmitError(String(err));
      setSubmitting(false);
    }
  };

  const maxEvents = Math.max(1, ...(repos ?? []).map((r) => r.event_counts.pr_bundle ?? 0));

  return (
    <>
      <section className="relative overflow-hidden">
        <div className="relative z-10 max-w-6xl mx-auto px-6 pt-20 pb-24 grid gap-16 lg:grid-cols-[1fr_0.92fr] lg:items-center">
          {/* Left: copy */}
          <div>
            <div className="rise inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[11px] tracking-[0.12em] text-fg-faint uppercase shadow-sm">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo" />
              Evidence-grounded repository history
            </div>

            <h1 className="rise mt-6 text-4xl sm:text-[3.1rem] font-bold tracking-tight leading-[1.08] text-fg" style={{ animationDelay: "60ms" }}>
              Which moments actually
              <br />
              <span className="text-gradient">shaped this codebase?</span>
            </h1>

            <p className="rise mt-5 max-w-lg text-[15px] leading-relaxed text-fg-dim" style={{ animationDelay: "140ms" }}>
              Repository interfaces show history in the order it happened, with every commit weighted the
              same. HistSig mines the full record — commits, issues, pull requests, reviews, releases —
              and ranks it into candidate historical events worth your attention.
            </p>

            <form onSubmit={onSubmit} className="rise mt-8 flex flex-col sm:flex-row gap-2.5 max-w-lg" style={{ animationDelay: "220ms" }}>
              <input
                type="text"
                required
                placeholder="https://github.com/owner/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                className="flex-1 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm text-fg placeholder:text-fg-faint outline-none transition focus:border-indigo/50 focus:ring-2 focus:ring-indigo/15"
              />
              <Button type="submit" disabled={submitting}>
                {submitting ? "Starting…" : "Analyze repository"}
              </Button>
            </form>
            {submitError && <p className="rise mt-3 text-sm text-red">{submitError}</p>}

            <a href="#repositories" className="rise mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-fg-dim hover:text-indigo transition-colors" style={{ animationDelay: "260ms" }}>
              Browse collected repositories <span aria-hidden="true">↓</span>
            </a>

            <div className="rise mt-11 grid gap-3 sm:grid-cols-3" style={{ animationDelay: "320ms" }}>
              {TRUST_ITEMS.map(({ Icon, title, body }) => (
                <div key={title} className="rounded-xl border border-line bg-surface px-3.5 py-3.5 shadow-sm">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo/[0.08] text-indigo">
                    <Icon />
                  </div>
                  <div className="mt-2.5 text-[13px] font-semibold text-fg">{title}</div>
                  <p className="mt-1 text-[12px] leading-relaxed text-fg-faint">{body}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Right: 3D graph + floating preview card */}
          <div className="relative h-[420px] sm:h-[480px]">
            <EventGraph className="absolute inset-0 z-0" />
            <div className="pointer-events-none absolute inset-0 z-[1] bg-[radial-gradient(60%_60%_at_50%_50%,transparent_40%,var(--bg)_92%)]" />

            <div className="float-soft rise absolute left-1/2 top-1/2 z-10 w-[300px] -translate-x-1/2 -translate-y-1/2 sm:w-[340px]" style={{ animationDelay: "180ms" }}>
              <Panel className="overflow-hidden shadow-xl shadow-indigo/10">
                <div className="flex items-center gap-1.5 border-b border-line bg-surface-alt px-4 py-2.5">
                  <span className="h-2 w-2 rounded-full bg-red/60" />
                  <span className="h-2 w-2 rounded-full bg-amber-soft/60" />
                  <span className="h-2 w-2 rounded-full bg-green/60" />
                  <span className="ml-2 text-[11px] font-medium text-fg-faint">Live coverage</span>
                </div>
                <div className="px-4 py-4 space-y-3">
                  {repos === null && (
                    <>
                      {[0, 1, 2].map((i) => (
                        <div key={i} className="panel sheen h-10" />
                      ))}
                    </>
                  )}
                  {repos !== null && repos.length === 0 && (
                    <p className="text-xs text-fg-faint">No repositories analyzed yet.</p>
                  )}
                  {repos?.slice(0, 4).map((r) => {
                    const count = r.event_counts.pr_bundle ?? 0;
                    const pct = Math.max(6, Math.round((count / maxEvents) * 100));
                    return (
                      <div key={r.safe_name}>
                        <div className="flex items-center justify-between text-[12px]">
                          <span className="truncate font-medium text-fg">{r.name}</span>
                          <span className="shrink-0 tabular-nums text-fg-faint">{count.toLocaleString()}</span>
                        </div>
                        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-alt">
                          <div className="h-full rounded-full bg-gradient-to-r from-indigo to-cyan-deep" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Panel>
            </div>
          </div>
        </div>
      </section>

      <main id="repositories" className="relative z-10 max-w-4xl mx-auto w-full px-6 py-12 scroll-mt-20">
        <SectionLabel>Collected repositories</SectionLabel>

        {error && (
          <Panel className="px-4 py-3 text-sm text-red">{error}</Panel>
        )}

        {!error && repos === null && (
          <div className="space-y-2">
            {[0, 1].map((i) => (
              <div key={i} className="panel sheen h-[68px]" />
            ))}
          </div>
        )}

        {repos !== null && repos.length === 0 && (
          <Panel className="px-6 py-10 text-center">
            <p className="text-sm text-fg-dim">Nothing collected yet.</p>
            <p className="mt-1 text-xs text-fg-faint">Paste a repository URL above to run the pipeline.</p>
          </Panel>
        )}

        <div className="space-y-2">
          {repos?.map((r, i) => (
            <Link key={r.safe_name} href={`/repos/${r.safe_name}`} className="block rise" style={{ animationDelay: `${i * 50}ms` }}>
              <Panel hover className="flex items-center justify-between gap-4 px-5 py-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{r.name}</span>
                    {r.event_counts.pr_bundle !== undefined && (
                      <Badge tone="pull_request">{r.event_counts.pr_bundle.toLocaleString()} events</Badge>
                    )}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-fg-faint tabular-nums">
                    <span>{r.counts.commits.toLocaleString()} commits</span>
                    <span>{r.counts.issues.toLocaleString()} issues</span>
                    <span>{r.counts.pull_requests.toLocaleString()} PRs</span>
                    <span>{r.counts.releases} releases</span>
                    {r.contributor_count !== null && <span>{r.contributor_count.toLocaleString()} contributors</span>}
                  </div>
                </div>
                <span className="shrink-0 text-[11px] text-fg-faint">
                  {new Date(r.collected_at).toLocaleDateString()}
                </span>
              </Panel>
            </Link>
          ))}
        </div>
      </main>
    </>
  );
}
