"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { BackLink, Panel, SectionLabel, Shell, Stat } from "../../components/ui";
import { api, RepoSummary } from "../../lib/api";

export default function RepoDetailPage({ params }: { params: Promise<{ safeName: string }> }) {
  const { safeName } = use(params);
  const [repo, setRepo] = useState<RepoSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getRepository(safeName)
      .then(setRepo)
      .catch((err) => setError(String(err)));
  }, [safeName]);

  return (
    <Shell width="max-w-3xl">
      <BackLink href="/">All repositories</BackLink>

      {error && <Panel className="mt-6 px-4 py-3 text-sm text-red">{error}</Panel>}

      {!error && repo === null && (
        <div className="mt-6 space-y-3">
          <div className="panel sheen h-14" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="panel sheen h-[62px]" />
            ))}
          </div>
        </div>
      )}

      {repo && (
        <div className="rise">
          <h1 className="mt-3 text-2xl font-semibold tracking-tight">{repo.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-faint">
            <a href={repo.url} target="_blank" rel="noreferrer" className="hover:text-cyan transition-colors">
              {repo.url}
            </a>
            <span className="text-line">•</span>
            <span>default branch <span className="font-mono text-fg-dim">{repo.default_branch}</span></span>
            <span className="text-line">•</span>
            <span>collected {new Date(repo.collected_at).toLocaleString()}</span>
          </div>

          <div className="mt-8">
            <SectionLabel>Raw evidence</SectionLabel>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Stat label="Commits" value={repo.counts.commits} accent="plain" />
              <Stat label="Issues" value={repo.counts.issues} accent="plain" />
              <Stat label="Pull requests" value={repo.counts.pull_requests} accent="plain" />
              <Stat label="Releases" value={repo.counts.releases} accent="plain" />
            </div>
          </div>

          <div className="mt-6">
            <SectionLabel>Derived</SectionLabel>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <Stat label="Contributors resolved" value={repo.contributor_count ?? "—"} accent="plain" />
              <Stat label="PR-bundle events" value={repo.event_counts.pr_bundle ?? "—"} accent="cyan" />
              <Stat label="Commit-level events" value={repo.event_counts.commit_level ?? "—"} accent="violet" />
            </div>
          </div>

          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            <Link href={`/repos/${safeName}/events?granularity=pr_bundle`}>
              <Panel hover className="h-full px-5 py-4">
                <div className="text-sm font-medium text-cyan">Browse PR-bundle events →</div>
                <p className="mt-1.5 text-xs leading-relaxed text-fg-faint">
                  Each pull request is one event bundling its commits; commits pushed outside any PR stand alone.
                </p>
              </Panel>
            </Link>
            <Link href={`/repos/${safeName}/events?granularity=commit_level`}>
              <Panel hover className="h-full px-5 py-4">
                <div className="text-sm font-medium text-violet">Browse commit-level events →</div>
                <p className="mt-1.5 text-xs leading-relaxed text-fg-faint">
                  Every commit as its own event, with no bundling — the alternative granularity, kept for comparison.
                </p>
              </Panel>
            </Link>
          </div>
        </div>
      )}
    </Shell>
  );
}
