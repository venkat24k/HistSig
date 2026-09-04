"use client";

import { use, useEffect, useState } from "react";
import { Badge, BackLink, Panel, SectionLabel, Shell } from "../../../../components/ui";
import { api, EventDetail } from "../../../../lib/api";

export default function EventDetailPage({ params }: { params: Promise<{ safeName: string; eventId: string }> }) {
  const { safeName, eventId } = use(params);
  const [event, setEvent] = useState<EventDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getEvent(safeName, Number(eventId))
      .then(setEvent)
      .catch((err) => setError(String(err)));
  }, [safeName, eventId]);

  return (
    <Shell width="max-w-3xl">
      <BackLink href={`/repos/${safeName}/events?granularity=${event?.granularity ?? "pr_bundle"}`}>Events</BackLink>

      {error && <Panel className="mt-6 px-4 py-3 text-sm text-red">{error}</Panel>}

      {!error && event === null && (
        <div className="mt-6 space-y-3">
          <div className="panel sheen h-20" />
          <div className="panel sheen h-40" />
        </div>
      )}

      {event && (
        <div className="rise">
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Badge tone={event.event_type}>{event.event_type.replace("_", " ")}</Badge>
            {event.source_pr_number !== null && (
              <span className="font-mono text-xs text-fg-faint">#{event.source_pr_number}</span>
            )}
            {event.pr_detail && <Badge tone={event.pr_detail.state}>{event.pr_detail.state}</Badge>}
          </div>

          <h1 className="mt-2.5 text-xl font-semibold leading-snug tracking-tight">{event.title}</h1>

          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-faint">
            <span>{new Date(event.occurred_at).toLocaleString()}</span>
            {event.author && (
              <>
                <span className="text-line">•</span>
                <span className="text-fg-dim">
                  {event.author.github_login ?? event.author.name ?? "unknown author"}
                  {event.author.is_bot && <span className="ml-1.5 text-amber">bot</span>}
                </span>
              </>
            )}
            {event.pr_detail && (
              <>
                <span className="text-line">•</span>
                <span className="font-mono">
                  {event.pr_detail.head_branch} <span className="text-fg-faint">→</span> {event.pr_detail.base_branch}
                </span>
              </>
            )}
          </div>

          {event.pr_detail?.body && (
            <div className="mt-7">
              <SectionLabel>Description</SectionLabel>
              <Panel className="px-5 py-4">
                <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-fg-dim">
                  {event.pr_detail.body}
                </pre>
              </Panel>
            </div>
          )}

          <div className="mt-7">
            <SectionLabel>Commits ({event.commits.length})</SectionLabel>
            <div className="space-y-1.5">
              {event.commits.map((c) => (
                <Panel key={c.hash} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-4">
                    <span className="min-w-0 truncate text-sm">
                      {c.message?.split("\n")[0] ?? (
                        <span className="italic text-fg-faint">
                          not in collected history — squash-merged or never merged
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-fg-faint">{c.hash.slice(0, 8)}</span>
                  </div>
                  {c.author_name && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 text-[11px] text-fg-faint">
                      <span>{c.author_name}</span>
                      {c.author_date_utc && (
                        <>
                          <span className="text-line">•</span>
                          <span>{new Date(c.author_date_utc).toLocaleDateString()}</span>
                        </>
                      )}
                      {c.insertions !== null && (
                        <>
                          <span className="text-line">•</span>
                          <span className="font-mono tabular-nums">
                            <span className="text-green">+{c.insertions}</span>{" "}
                            <span className="text-red">−{c.deletions}</span>
                          </span>
                        </>
                      )}
                    </div>
                  )}
                </Panel>
              ))}
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}
