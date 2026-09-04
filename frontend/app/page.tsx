"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ParticleField from "./components/ParticleField";
import { Badge, Panel, SectionLabel } from "./components/ui";
import { api, RepoSummary } from "./lib/api";

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

  return (
    <>
      <section className="relative overflow-hidden border-b border-line-soft/70">
        <ParticleField className="absolute inset-0 z-0" />
        {/* Keeps copy legible over the point cloud without hiding it: a soft
            well behind the text block, and a stronger fade only at the edges. */}
        <div className="absolute inset-0 z-[1] bg-[radial-gradient(46%_46%_at_50%_44%,rgba(7,7,12,0.86),rgba(7,7,12,0.30)_62%,rgba(7,7,12,0.72))]" />
        <div className="absolute inset-x-0 bottom-0 z-[1] h-28 bg-gradient-to-b from-transparent to-ink-900" />

        <div className="relative z-10 max-w-4xl mx-auto px-6 pt-24 pb-24 text-center">
          <div className="rise inline-flex items-center gap-2 rounded-full border border-line px-3 py-1 text-[11px] tracking-[0.12em] text-fg-faint uppercase mb-7">
            <span className="h-1 w-1 rounded-full bg-cyan" />
            Stage 3 · candidate events
          </div>

          <h1 className="rise text-4xl sm:text-5xl font-semibold tracking-tight leading-[1.08] text-gradient" style={{ animationDelay: "60ms" }}>
            Which moments actually
            <br />
            shaped this codebase?
          </h1>

          <p className="rise mx-auto mt-5 max-w-xl text-sm sm:text-[15px] leading-relaxed text-fg-dim" style={{ animationDelay: "140ms" }}>
            Repository interfaces show history in the order it happened, with every commit weighted the
            same. Digital Ghost mines the full record — commits, issues, pull requests, reviews,
            releases — and reassembles it into candidate historical events worth ranking.
          </p>

          <form onSubmit={onSubmit} className="rise mx-auto mt-9 flex max-w-xl gap-2" style={{ animationDelay: "220ms" }}>
            <input
              type="text"
              required
              placeholder="https://github.com/owner/repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              className="flex-1 rounded-lg border border-line bg-ink-800/80 px-4 py-2.5 text-sm text-fg placeholder:text-fg-faint outline-none transition focus:border-cyan-deep/60 focus:ring-2 focus:ring-cyan-deep/15"
            />
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-cyan-deep px-5 py-2.5 text-sm font-medium text-ink-900 transition hover:bg-cyan disabled:opacity-45"
            >
              {submitting ? "Starting…" : "Analyze"}
            </button>
          </form>

          {submitError && <p className="mt-3 text-sm text-red">{submitError}</p>}

          <div className="rise mt-7 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-[11px] text-fg-faint" style={{ animationDelay: "300ms" }}>
            <span>PyDriller + GitHub GraphQL</span>
            <span className="text-line">•</span>
            <span>Identity resolution &amp; rename tracking</span>
            <span className="text-line">•</span>
            <span>Two event granularities</span>
          </div>
        </div>
      </section>

      <main className="relative z-10 max-w-4xl mx-auto w-full px-6 py-12">
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
