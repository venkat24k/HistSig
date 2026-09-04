"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useEffect, useState } from "react";
import { Badge, BackLink, Panel, Shell } from "../../../components/ui";
import { api, EventList } from "../../../lib/api";

const PAGE_SIZE = 25;

export default function EventsListPage({ params }: { params: Promise<{ safeName: string }> }) {
  const { safeName } = use(params);
  const searchParams = useSearchParams();
  const router = useRouter();

  const granularity = searchParams.get("granularity") === "commit_level" ? "commit_level" : "pr_bundle";
  const offset = Number(searchParams.get("offset") ?? "0");
  const eventType = searchParams.get("event_type");

  const [data, setData] = useState<EventList | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api
      .listEvents(safeName, granularity, offset, PAGE_SIZE, eventType)
      .then(setData)
      .catch((err) => setError(String(err)));
  }, [safeName, granularity, offset, eventType]);

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams.toString());
    if (value === null) next.delete(key);
    else next.set(key, value);
    // Changing a filter resets to the first page; changing the page itself
    // obviously must not wipe the offset it just set.
    if (key !== "offset") next.delete("offset");
    router.push(`/repos/${safeName}/events?${next.toString()}`);
  };

  const eventTypes = granularity === "pr_bundle" ? ["pull_request", "standalone_commit"] : ["commit"];
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <Shell width="max-w-4xl">
      <BackLink href={`/repos/${safeName}`}>Repository</BackLink>
      <h1 className="mt-3 text-xl font-semibold tracking-tight">Candidate events</h1>
      <p className="mt-1 text-sm text-fg-dim">
        {granularity === "pr_bundle"
          ? "Pull requests bundled with their commits, plus commits that never belonged to one."
          : "Every commit treated as its own event, with no bundling."}
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <Segmented
          options={[
            { value: "pr_bundle", label: "PR-bundle" },
            { value: "commit_level", label: "Commit-level" },
          ]}
          value={granularity}
          onChange={(v) => setParam("granularity", v)}
        />
        <div className="flex items-center gap-1.5">
          <Chip active={!eventType} onClick={() => setParam("event_type", null)}>
            All
          </Chip>
          {eventTypes.map((t) => (
            <Chip key={t} active={eventType === t} onClick={() => setParam("event_type", t)}>
              {t.replace("_", " ")}
            </Chip>
          ))}
        </div>
      </div>

      {error && <Panel className="mt-6 px-4 py-3 text-sm text-red">{error}</Panel>}

      {!error && data === null && (
        <div className="mt-6 space-y-2">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="panel sheen h-[58px]" />
          ))}
        </div>
      )}

      {data && (
        <>
          <p className="mt-6 mb-2 text-[11px] tracking-wide text-fg-faint tabular-nums">
            {data.total.toLocaleString()} events
          </p>

          <div className="space-y-1.5">
            {data.events.map((e, i) => (
              <Link
                key={e.id}
                href={`/repos/${safeName}/events/${e.id}`}
                className="block rise"
                style={{ animationDelay: `${Math.min(i * 22, 260)}ms` }}
              >
                <Panel hover className="flex items-center justify-between gap-4 px-4 py-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-fg">{e.title}</div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-fg-faint">
                      <Badge tone={e.event_type}>{e.event_type.replace("_", " ")}</Badge>
                      {e.source_pr_number !== null && <span className="font-mono">#{e.source_pr_number}</span>}
                      {e.primary_commit_hash && (
                        <span className="font-mono">{e.primary_commit_hash.slice(0, 8)}</span>
                      )}
                      {e.author?.github_login && (
                        <span>
                          {e.author.github_login}
                          {e.author.is_bot && <span className="ml-1 text-amber">bot</span>}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className="shrink-0 text-[11px] text-fg-faint tabular-nums">
                    {new Date(e.occurred_at).toLocaleDateString()}
                  </span>
                </Panel>
              </Link>
            ))}

            {data.events.length === 0 && (
              <Panel className="px-6 py-10 text-center text-sm text-fg-dim">No events match this filter.</Panel>
            )}
          </div>

          {data.total > PAGE_SIZE && (
            <div className="mt-6 flex items-center justify-between">
              <PageButton disabled={offset === 0} onClick={() => setParam("offset", String(Math.max(0, offset - PAGE_SIZE)))}>
                ← Previous
              </PageButton>
              <span className="text-[11px] text-fg-faint tabular-nums">
                {(offset + 1).toLocaleString()}–{Math.min(offset + PAGE_SIZE, data.total).toLocaleString()} of{" "}
                {data.total.toLocaleString()}
                <span className="mx-2 text-line">|</span>
                page {page.toLocaleString()} / {totalPages.toLocaleString()}
              </span>
              <PageButton
                disabled={offset + PAGE_SIZE >= data.total}
                onClick={() => setParam("offset", String(offset + PAGE_SIZE))}
              >
                Next →
              </PageButton>
            </div>
          )}
        </>
      )}
    </Shell>
  );
}

function Segmented({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-ink-800/60 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-[6px] px-3 py-1.5 text-xs font-medium transition ${
            value === o.value ? "bg-cyan-deep text-ink-900" : "text-fg-dim hover:text-fg"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md border px-2.5 py-1 text-[11px] capitalize transition ${
        active ? "border-cyan-deep/45 bg-cyan-deep/10 text-cyan" : "border-line text-fg-faint hover:text-fg-dim"
      }`}
    >
      {children}
    </button>
  );
}

function PageButton({ disabled, onClick, children }: { disabled: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className="rounded-lg border border-line px-3 py-1.5 text-xs text-fg-dim transition hover:border-cyan-deep/40 hover:text-cyan disabled:opacity-30 disabled:hover:border-line disabled:hover:text-fg-dim"
    >
      {children}
    </button>
  );
}
