"use client";

import { use, useEffect, useState } from "react";
import { Badge, BackLink, Panel, SectionLabel, Shell } from "../../../../components/ui";
import {
  api,
  EventDetail,
  P_FEATURE_LABELS,
  PFeatureValue,
  QUADRANT_DESCRIPTIONS,
  QUADRANT_LABELS,
  R_FEATURE_LABELS,
  RFeatureValue,
} from "../../../../lib/api";

function formatPValue(name: string, entry: PFeatureValue): string {
  if (entry.value === null) return "—";
  if (typeof entry.value === "boolean") return entry.value ? "Yes" : "No";
  if (name === "release_proximity" && typeof entry.value === "number") {
    const days = entry.value / 86400;
    return days < 1 ? `${Math.round(entry.value / 3600)}h` : `${days.toFixed(1)}d`;
  }
  return entry.value.toLocaleString();
}

function formatRValue(entry: RFeatureValue): string {
  if (entry.value === null) return "—";
  return entry.value.toLocaleString();
}

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
          <div className="panel sheen h-28" />
          <div className="panel sheen h-44" />
        </div>
      )}

      {event && (
        <div className="rise">
          <Panel className="mt-6 px-6 py-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={event.event_type}>{event.event_type.replace("_", " ")}</Badge>
                  {event.p_score?.is_high_p && <Badge tone="high-p">high P</Badge>}
                  {event.r_score?.is_high_r && <Badge tone="high-r">high R</Badge>}
                  {event.divergence && <Badge tone={event.divergence.quadrant}>{QUADRANT_LABELS[event.divergence.quadrant]}</Badge>}
                  {event.source_pr_number !== null && (
                    <span className="font-mono text-xs text-fg-faint">#{event.source_pr_number}</span>
                  )}
                  {event.pr_detail && <Badge tone={event.pr_detail.state}>{event.pr_detail.state}</Badge>}
                </div>

                <h1 className="mt-3 text-xl font-bold leading-snug tracking-tight text-fg">{event.title}</h1>

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
              </div>

              <div className="flex shrink-0 items-start gap-3">
                {event.p_score?.p_score !== null && event.p_score?.p_score !== undefined && (
                  <div className="text-center">
                    <div
                      className={`flex h-16 w-16 items-center justify-center rounded-full border-[3px] text-lg font-bold tabular-nums ${
                        event.p_score.is_high_p ? "border-amber text-amber bg-amber/[0.06]" : "border-line text-fg-dim bg-surface-alt"
                      }`}
                    >
                      {event.p_score.p_score.toFixed(2)}
                    </div>
                    <div className="mt-1.5 text-[10px] font-medium tracking-[0.08em] text-fg-faint uppercase">P score</div>
                  </div>
                )}
                {event.r_score?.r_score !== null && event.r_score?.r_score !== undefined && (
                  <div className="text-center">
                    <div
                      className={`flex h-16 w-16 items-center justify-center rounded-full border-[3px] text-lg font-bold tabular-nums ${
                        event.r_score.is_high_r ? "border-violet-deep text-violet-deep bg-violet-deep/[0.06]" : "border-line text-fg-dim bg-surface-alt"
                      }`}
                    >
                      {event.r_score.r_score.toFixed(2)}
                    </div>
                    <div className="mt-1.5 text-[10px] font-medium tracking-[0.08em] text-fg-faint uppercase">R score</div>
                  </div>
                )}
              </div>
            </div>
          </Panel>

          {event.divergence && (
            <Panel className="mt-3 px-5 py-3">
              <p className="text-xs text-fg-dim">
                <span className="font-semibold text-fg">{QUADRANT_LABELS[event.divergence.quadrant]}</span>
                {" — "}
                {QUADRANT_DESCRIPTIONS[event.divergence.quadrant]}
              </p>
            </Panel>
          )}

          <div className="mt-7">
            <div className="flex items-start justify-between">
              <SectionLabel>Perceived Significance (P)</SectionLabel>
              {event.p_score?.p_score !== null && event.p_score?.p_score !== undefined && (
                <span className={`font-mono text-xs tabular-nums ${event.p_score.is_high_p ? "text-amber" : "text-fg-faint"}`}>
                  {event.p_score.is_high_p ? "top 10% of its group" : "within group's typical range"}
                </span>
              )}
            </div>
            {event.p_features === null ? (
              <Panel className="px-4 py-3 text-sm text-fg-faint">
                Not yet computed for this repository — run Stage 2 feature extraction.
              </Panel>
            ) : (
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {Object.entries(event.p_features).map(([name, entry]) => (
                  <Panel key={name} className="px-3 py-2.5">
                    <div className="text-[11px] text-fg-faint">{P_FEATURE_LABELS[name] ?? name}</div>
                    <div className="mt-1 flex items-baseline gap-1.5">
                      <span
                        className={`text-base font-semibold tabular-nums ${
                          entry.status === "not_applicable" ? "text-fg-faint" : "text-indigo"
                        }`}
                      >
                        {entry.status === "incomplete_lower_bound" && entry.value !== null ? "≥ " : ""}
                        {formatPValue(name, entry)}
                      </span>
                      {entry.status === "incomplete_lower_bound" && (
                        <span className="text-[10px] text-amber">lower bound</span>
                      )}
                    </div>
                  </Panel>
                ))}
              </div>
            )}
          </div>

          <div className="mt-7">
            <div className="flex items-start justify-between">
              <SectionLabel>Historical Salience (R)</SectionLabel>
              <div className="flex flex-col items-end gap-0.5">
                {event.r_score && event.r_score.r_score !== null ? (
                  <span className={`font-mono text-xs tabular-nums ${event.r_score.is_high_r ? "text-violet-deep" : "text-fg-faint"}`}>
                    {event.r_score.is_high_r ? "top 10% of its group" : "within group's typical range"}
                  </span>
                ) : (
                  event.r_score && (
                    <span className="font-mono text-xs tabular-nums text-fg-faint">too young to rank yet</span>
                  )
                )}
                {event.r_features?.maturity.status === "complete" && event.r_features.maturity.value !== null && (
                  <span className="font-mono text-xs tabular-nums text-violet">
                    maturity {Math.round(event.r_features.maturity.value * 100)}%
                  </span>
                )}
              </div>
            </div>
            {event.r_features === null ? (
              <Panel className="px-4 py-3 text-sm text-fg-faint">
                Not yet computed for this repository — run Stage 3 R feature extraction.
              </Panel>
            ) : (
              <>
                {event.r_features.maturity.status !== "complete" ? (
                  <p className="mb-2 text-xs text-fg-faint">
                    Maturity not available — this event falls outside the repository&apos;s observed commit window.
                  </p>
                ) : (
                  <p className="mb-2 text-xs text-fg-faint">
                    {Math.round(event.r_features.maturity.value! * 100)}% of this repository&apos;s observed history happened
                    after this event{event.r_features.maturity.value! < 0.1 ? " — too early to judge lasting impact yet" : ""}.
                  </p>
                )}
                <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                  {Object.entries(event.r_features.features).map(([name, entry]) => (
                    <Panel key={name} className="px-3 py-2.5">
                      <div className="text-[11px] text-fg-faint">{R_FEATURE_LABELS[name] ?? name}</div>
                      <div className="mt-1 flex items-baseline gap-1.5">
                        <span
                          className={`text-base font-semibold tabular-nums ${
                            entry.status === "not_applicable" ? "text-fg-faint" : "text-violet"
                          }`}
                        >
                          {entry.status === "incomplete_lower_bound" && entry.value !== null ? "≥ " : ""}
                          {formatRValue(entry)}
                        </span>
                        {entry.status === "incomplete_lower_bound" && (
                          <span className="text-[10px] text-amber">lower bound</span>
                        )}
                      </div>
                    </Panel>
                  ))}
                </div>
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
                <CommitRow key={c.hash} safeName={safeName} commit={c} />
              ))}
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}

function CommitRow({ safeName, commit: c }: { safeName: string; commit: EventDetail["commits"][number] }) {
  const [open, setOpen] = useState(false);
  const [diff, setDiff] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  const foundLocally = c.message !== null;

  const explain = () => {
    if (explaining || explanation !== null) return;
    setExplaining(true);
    setExplainError(null);
    api
      .explainCommitDiff(safeName, c.hash)
      .then((d) => setExplanation(d.explanation))
      .catch((err) => setExplainError(String(err)))
      .finally(() => setExplaining(false));
  };

  const toggle = () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (diff !== null || loading) return;
    setLoading(true);
    setError(null);
    api
      .getCommitDiff(safeName, c.hash)
      .then((d) => {
        setDiff(d.diff);
        setTruncated(d.truncated);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  };

  return (
    <Panel className="px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <span className="min-w-0 truncate text-sm text-fg">
          {c.message?.split("\n")[0] ?? (
            <span className="italic text-fg-faint">not in collected history — squash-merged or never merged</span>
          )}
        </span>
        <span className="shrink-0 rounded-md bg-surface-alt px-1.5 py-0.5 font-mono text-[11px] text-fg-faint">
          {c.hash.slice(0, 8)}
        </span>
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
                <span className="text-green">+{c.insertions}</span> <span className="text-red">−{c.deletions}</span>
              </span>
            </>
          )}
          {foundLocally && (
            <>
              <span className="text-line">•</span>
              <button onClick={toggle} className="font-medium text-indigo hover:underline">
                {open ? "Hide diff" : "View diff"}
              </button>
            </>
          )}
        </div>
      )}

      {open && foundLocally && (
        <div className="mt-2.5">
          {loading && <div className="panel sheen h-24" />}
          {error && <p className="rounded-lg bg-red/[0.06] px-3 py-2 text-xs text-red">{error}</p>}
          {diff !== null && (
            <>
              <DiffView diff={diff} />
              {truncated && <p className="mt-1.5 text-[11px] text-fg-faint">Diff truncated — showing the first portion only.</p>}

              <div className="mt-2">
                {explanation === null && !explaining && (
                  <button onClick={explain} className="text-[11px] font-medium text-indigo hover:underline">
                    Explain this diff (AI, optional)
                  </button>
                )}
                {explaining && <div className="panel sheen h-14" />}
                {explainError && (
                  <p className="rounded-lg bg-red/[0.06] px-3 py-2 text-xs text-red">{explainError}</p>
                )}
                {explanation !== null && (
                  <div className="rounded-lg border border-cyan-deep/20 bg-cyan-deep/[0.05] px-3.5 py-3">
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-cyan-deep">
                      AI explanation — generated from the diff above, not verified evidence
                    </p>
                    <p className="text-[13px] leading-relaxed text-fg-dim">{explanation}</p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </Panel>
  );
}

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-fg-faint";
  if (line.startsWith("+")) return "text-green";
  if (line.startsWith("-")) return "text-red";
  if (line.startsWith("@@")) return "text-indigo";
  if (line.startsWith("diff --git") || line.startsWith("index ")) return "text-fg-faint font-semibold";
  return "text-fg-dim";
}

function DiffView({ diff }: { diff: string }) {
  if (diff.trim() === "") {
    return <p className="text-xs italic text-fg-faint">No textual diff (binary file, or a merge with no conflicting hunks).</p>;
  }
  const lines = diff.split("\n");
  return (
    <pre className="max-h-[32rem] overflow-auto rounded-lg border border-line bg-surface-alt px-3.5 py-3 font-mono text-[12px] leading-relaxed">
      {lines.map((line, i) => (
        <div key={i} className={diffLineClass(line)}>
          {line || " "}
        </div>
      ))}
    </pre>
  );
}
