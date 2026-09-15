"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useEffect, useState } from "react";
import { Badge, BackLink, Panel, Shell } from "../../../components/ui";
import {
  api,
  DivergenceSummary,
  EventList,
  EventSummary,
  GroupThreshold,
  PRHeatmap,
  Quadrant,
  QUADRANT_DESCRIPTIONS,
  QUADRANT_LABELS,
  QUADRANTS,
} from "../../../lib/api";

const PAGE_SIZE = 25;
const GROUP_PREVIEW_SIZE = 5;

const EVENT_TYPE_LABELS: Record<string, string> = {
  pull_request: "Pull Request",
  standalone_commit: "Standalone Commit",
  commit: "Commit",
};

const TYPES_BY_GRANULARITY: Record<string, string[]> = {
  pr_bundle: ["pull_request", "standalone_commit"],
  commit_level: ["commit"],
};

function parseAttention(param: string | null): boolean | null {
  return param === "high" ? true : param === "rest" ? false : null;
}

export default function EventsListPage({ params }: { params: Promise<{ safeName: string }> }) {
  const { safeName } = use(params);
  const searchParams = useSearchParams();
  const router = useRouter();

  const granularity = searchParams.get("granularity") === "commit_level" ? "commit_level" : "pr_bundle";
  const offset = Number(searchParams.get("offset") ?? "0");
  const eventType = searchParams.get("event_type");
  const pAttentionParam = searchParams.get("p_attention");
  const rAttentionParam = searchParams.get("r_attention");
  const highP = parseAttention(pAttentionParam);
  const highR = parseAttention(rAttentionParam);
  const quadrantParam = searchParams.get("quadrant");
  const quadrant = QUADRANTS.includes(quadrantParam as Quadrant) ? (quadrantParam as Quadrant) : null;

  const [data, setData] = useState<EventList | null>(null);
  const [error, setError] = useState<string | null>(null);

  // When "high/rest" attention is picked with no specific type, one flat
  // list would silently mix groups with different thresholds together —
  // exactly the "0.65 is high-P but 0.7 isn't" confusion. Instead, split
  // into one section per event_type, each with its own threshold shown.
  const grouped = (highP !== null || highR !== null) && !eventType;
  const eventTypes = TYPES_BY_GRANULARITY[granularity];

  useEffect(() => {
    if (grouped) return;
    setData(null);
    api
      .listEvents(safeName, granularity, offset, PAGE_SIZE, eventType, highP, highR, quadrant)
      .then(setData)
      .catch((err) => setError(String(err)));
  }, [safeName, granularity, offset, eventType, highP, highR, quadrant, grouped]);

  const setParam = (updates: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    if (!("offset" in updates)) next.delete("offset");
    router.push(`/repos/${safeName}/events?${next.toString()}`);
  };

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <Shell width="max-w-4xl">
      <BackLink href={`/repos/${safeName}`}>Repository</BackLink>
      <h1 className="mt-3 text-2xl font-bold tracking-tight">Candidate events</h1>
      <p className="mt-1 text-sm text-fg-dim">
        {granularity === "pr_bundle"
          ? "Pull requests bundled with their commits, plus commits that never belonged to one."
          : "Every commit treated as its own event, with no bundling."}
      </p>

      <Panel className="mt-6 px-4 py-4">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
          <div>
            <FilterLabel>Granularity</FilterLabel>
            <Segmented
              options={[
                { value: "pr_bundle", label: "PR-bundle" },
                { value: "commit_level", label: "Commit-level" },
              ]}
              value={granularity}
              onChange={(v) => setParam({ granularity: v, event_type: null })}
            />
          </div>
          <div className="min-w-[170px]">
            <FilterLabel>Type</FilterLabel>
            <FilterSelect
              value={eventType ?? ""}
              onChange={(v) => setParam({ event_type: v || null })}
              options={[
                { value: "", label: "All types" },
                ...eventTypes.map((t) => ({ value: t, label: EVENT_TYPE_LABELS[t] })),
              ]}
            />
          </div>
          <div className="min-w-[190px]">
            <FilterLabel>P attention</FilterLabel>
            <FilterSelect
              value={pAttentionParam ?? ""}
              onChange={(v) => setParam({ p_attention: v || null })}
              options={[
                { value: "", label: "All events" },
                { value: "high", label: "High P only" },
                { value: "rest", label: "Rest (not high P)" },
              ]}
            />
          </div>
          <div className="min-w-[190px]">
            <FilterLabel>R attention</FilterLabel>
            <FilterSelect
              value={rAttentionParam ?? ""}
              onChange={(v) => setParam({ r_attention: v || null })}
              options={[
                { value: "", label: "All events" },
                { value: "high", label: "High R only" },
                { value: "rest", label: "Rest (not high R)" },
              ]}
            />
          </div>
          <div className="min-w-[210px]">
            <FilterLabel>Divergence quadrant</FilterLabel>
            <FilterSelect
              value={quadrant ?? ""}
              onChange={(v) => setParam({ quadrant: v || null })}
              options={[
                { value: "", label: "All quadrants" },
                ...QUADRANTS.map((q) => ({ value: q, label: QUADRANT_LABELS[q] })),
              ]}
            />
          </div>
        </div>
      </Panel>

      <DivergenceOverview safeName={safeName} granularity={granularity} selected={quadrant} onSelect={(q) => setParam({ quadrant: q })} />

      <PRHeatmapChart safeName={safeName} granularity={granularity} />

      {error && <Panel className="mt-6 px-4 py-3 text-sm text-red">{error}</Panel>}

      {grouped ? (
        <div className="mt-6 space-y-7">
          {eventTypes.map((t) => (
            <EventTypeGroup
              key={t}
              safeName={safeName}
              granularity={granularity}
              eventType={t}
              highP={highP}
              highR={highR}
              quadrant={quadrant}
            />
          ))}
        </div>
      ) : (
        <>
          {!error && data === null && (
            <div className="mt-6 space-y-2">
              {Array.from({ length: 8 }, (_, i) => (
                <div key={i} className="panel sheen h-[58px]" />
              ))}
            </div>
          )}

          {data && (
            <>
              <div className="mt-6 mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] tracking-wide text-fg-faint tabular-nums">{data.total.toLocaleString()} events</p>
                {eventType && (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                    {data.p_thresholds[eventType] && (
                      <ThresholdNote axis="P" label={EVENT_TYPE_LABELS[eventType]} threshold={data.p_thresholds[eventType]} />
                    )}
                    {data.r_thresholds[eventType] && (
                      <ThresholdNote axis="R" label={EVENT_TYPE_LABELS[eventType]} threshold={data.r_thresholds[eventType]} />
                    )}
                  </div>
                )}
              </div>

              <div className="space-y-1.5">
                {data.events.map((e, i) => (
                  <EventRow key={e.id} event={e} safeName={safeName} delay={Math.min(i * 22, 260)} />
                ))}
                {data.events.length === 0 && (
                  <Panel className="px-6 py-10 text-center text-sm text-fg-dim">No events match this filter.</Panel>
                )}
              </div>

              {data.total > PAGE_SIZE && (
                <div className="mt-6 flex items-center justify-between">
                  <PageButton disabled={offset === 0} onClick={() => setParam({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}>
                    ← Previous
                  </PageButton>
                  <span className="text-[11px] text-fg-faint tabular-nums">
                    {(offset + 1).toLocaleString()}–{Math.min(offset + PAGE_SIZE, data.total).toLocaleString()} of{" "}
                    {data.total.toLocaleString()}
                    <span className="mx-2 text-line">|</span>
                    page {page.toLocaleString()} / {totalPages.toLocaleString()}
                  </span>
                  <PageButton disabled={offset + PAGE_SIZE >= data.total} onClick={() => setParam({ offset: String(offset + PAGE_SIZE) })}>
                    Next →
                  </PageButton>
                </div>
              )}
            </>
          )}
        </>
      )}
    </Shell>
  );
}

function EventTypeGroup({
  safeName,
  granularity,
  eventType,
  highP,
  highR,
  quadrant,
}: {
  safeName: string;
  granularity: string;
  eventType: string;
  highP: boolean | null;
  highR: boolean | null;
  quadrant: Quadrant | null;
}) {
  const [data, setData] = useState<EventList | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api
      .listEvents(safeName, granularity, 0, GROUP_PREVIEW_SIZE, eventType, highP, highR, quadrant)
      .then(setData)
      .catch((err) => setError(String(err)));
  }, [safeName, granularity, eventType, highP, highR, quadrant]);

  const pThreshold = data?.p_thresholds[eventType];
  const rThreshold = data?.r_thresholds[eventType];
  const viewAllParams = new URLSearchParams({ granularity, event_type: eventType });
  if (highP !== null) viewAllParams.set("p_attention", highP ? "high" : "rest");
  if (highR !== null) viewAllParams.set("r_attention", highR ? "high" : "rest");
  if (quadrant) viewAllParams.set("quadrant", quadrant);
  const viewAllHref = `/repos/${safeName}/events?${viewAllParams.toString()}`;

  return (
    <div>
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge tone={eventType}>{EVENT_TYPE_LABELS[eventType]}</Badge>
          <span className="text-[11px] text-fg-faint tabular-nums">{data ? `${data.total.toLocaleString()} events` : "…"}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {pThreshold && <ThresholdNote axis="P" label={EVENT_TYPE_LABELS[eventType]} threshold={pThreshold} compact />}
          {rThreshold && <ThresholdNote axis="R" label={EVENT_TYPE_LABELS[eventType]} threshold={rThreshold} compact />}
        </div>
      </div>

      {error && <Panel className="px-4 py-3 text-sm text-red">{error}</Panel>}

      {!error && data === null && (
        <div className="space-y-1.5">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="panel sheen h-[58px]" />
          ))}
        </div>
      )}

      {data && data.events.length === 0 && (
        <Panel className="px-5 py-6 text-center text-sm text-fg-dim">
          No {EVENT_TYPE_LABELS[eventType].toLowerCase()} events match this filter.
        </Panel>
      )}

      {data && data.events.length > 0 && (
        <div className="space-y-1.5">
          {data.events.map((e, i) => (
            <EventRow key={e.id} event={e} safeName={safeName} delay={Math.min(i * 22, 200)} />
          ))}
          {data.total > GROUP_PREVIEW_SIZE && (
            <Link href={viewAllHref} className="block px-1 pt-1 text-[12px] font-medium text-indigo hover:underline">
              View all {data.total.toLocaleString()} {EVENT_TYPE_LABELS[eventType].toLowerCase()} events →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

function DivergenceOverview({
  safeName,
  granularity,
  selected,
  onSelect,
}: {
  safeName: string;
  granularity: string;
  selected: Quadrant | null;
  onSelect: (quadrant: Quadrant | null) => void;
}) {
  const [summary, setSummary] = useState<DivergenceSummary | null>(null);

  useEffect(() => {
    setSummary(null);
    api.getDivergenceSummary(safeName, granularity).then(setSummary).catch(() => setSummary(null));
  }, [safeName, granularity]);

  const total = summary ? Object.values(summary.counts).reduce((a, b) => a + b, 0) : 0;
  if (summary && total === 0) return null;

  return (
    <div className="mt-4">
      <div className="mb-2 flex items-baseline justify-between">
        <FilterLabel>Divergence — Perceived Significance × Historical Salience</FilterLabel>
        {selected && (
          <button onClick={() => onSelect(null)} className="text-[11px] text-indigo hover:underline">
            clear selection
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {QUADRANTS.map((q) => (
          <button key={q} onClick={() => onSelect(selected === q ? null : q)} className="text-left">
            <Panel
              hover
              className={`px-3.5 py-3 transition ${selected === q ? "ring-2 ring-indigo/40 border-indigo/40" : ""}`}
            >
              <div className="flex items-center justify-between gap-2">
                <Badge tone={q}>{QUADRANT_LABELS[q]}</Badge>
              </div>
              <div className="mt-2 text-xl font-semibold tabular-nums text-fg">
                {summary ? summary.counts[q].toLocaleString() : "…"}
              </div>
              <p className="mt-1 text-[11px] leading-snug text-fg-faint">{QUADRANT_DESCRIPTIONS[q]}</p>
            </Panel>
          </button>
        ))}
      </div>
    </div>
  );
}

// Sequential single-hue ramp (blue, light -> dark), 3 key stops taken
// directly from the design system's documented sequential palette --
// continuous colors are linearly interpolated between adjacent stops
// rather than stepped, since a heatmap encodes a continuous magnitude,
// not a small set of ordinal buckets.
const HEAT_RAMP: [number, [number, number, number]][] = [
  [0, [0xcd, 0xe2, 0xfb]],
  [0.5, [0x39, 0x87, 0xe5]],
  [1, [0x0d, 0x36, 0x6b]],
];

function heatColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const i = clamped <= 0.5 ? 0 : 1;
  const [t0, c0] = HEAT_RAMP[i];
  const [t1, c1] = HEAT_RAMP[i + 1];
  const local = (clamped - t0) / (t1 - t0);
  const rgb = c0.map((v, k) => Math.round(v + (c1[k] - v) * local));
  return `rgb(${rgb.join(", ")})`;
}

function PRHeatmapChart({ safeName, granularity }: { safeName: string; granularity: string }) {
  const [data, setData] = useState<PRHeatmap | null>(null);
  const [hovered, setHovered] = useState<{ p_bin: number; r_bin: number; count: number } | null>(null);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    setData(null);
    setHovered(null);
    api
      .getPRHeatmap(safeName, granularity, 10)
      .then(setData)
      .catch(() => setData({ granularity, bins: 10, total: 0, cells: [] }));
  }, [safeName, granularity]);

  if (data && data.total === 0) return null;

  const bins = data?.bins ?? 10;
  const maxCount = data ? Math.max(1, ...data.cells.map((c) => c.count)) : 1;
  const cellByPos = new Map((data?.cells ?? []).map((c) => [`${c.p_bin}-${c.r_bin}`, c.count]));
  const binLabel = (bin: number) => `${(bin / bins).toFixed(1)}–${((bin + 1) / bins).toFixed(1)}`;
  const rowOrder = Array.from({ length: bins }, (_, i) => bins - 1 - i); // R high (top) -> low (bottom)
  const colOrder = Array.from({ length: bins }, (_, i) => i); // P low (left) -> high (right)
  const cellPx = 22;

  return (
    <div className="mt-6">
      <div className="mb-2 flex items-baseline justify-between">
        <FilterLabel>P / R concentration heatmap</FilterLabel>
        {data && data.total > 0 && (
          <button onClick={() => setShowTable((v) => !v)} className="text-[11px] text-indigo hover:underline">
            {showTable ? "Show as chart" : "Show as table"}
          </button>
        )}
      </div>
      <Panel className="px-5 py-4">
        {!data && <div className="h-64 panel sheen" />}
        {data && (
          <>
            <p className="mb-3 min-h-[14px] text-[11px] text-fg-faint">
              {hovered
                ? `P ${binLabel(hovered.p_bin)} × R ${binLabel(hovered.r_bin)} — ${hovered.count.toLocaleString()} event${hovered.count === 1 ? "" : "s"}`
                : `${data.total.toLocaleString()} events scored on both axes — hover a cell for its exact P/R range and count`}
            </p>

            {!showTable ? (
              <div className="flex gap-2.5 overflow-x-auto pb-1">
                <div className="flex shrink-0 flex-col items-center justify-between py-0.5 text-[10px] text-fg-faint">
                  <span>1.0</span>
                  <span className="whitespace-nowrap [writing-mode:vertical-rl] rotate-180 tracking-wide">
                    Historical Salience (R)
                  </span>
                  <span>0.0</span>
                </div>
                <div className="shrink-0">
                  <div className="inline-grid gap-[2px]" style={{ gridTemplateColumns: `repeat(${bins}, ${cellPx}px)` }}>
                    {rowOrder.map((r) =>
                      colOrder.map((p) => {
                        const count = cellByPos.get(`${p}-${r}`) ?? 0;
                        const t = count === 0 ? 0 : Math.log1p(count) / Math.log1p(maxCount);
                        return (
                          <div
                            key={`${p}-${r}`}
                            title={`P ${binLabel(p)} × R ${binLabel(r)}: ${count} events`}
                            onMouseEnter={() => setHovered({ p_bin: p, r_bin: r, count })}
                            onMouseLeave={() => setHovered(null)}
                            className="rounded-[3px] transition hover:ring-2 hover:ring-indigo/50"
                            style={{
                              width: cellPx, height: cellPx,
                              background: count === 0 ? "var(--color-surface-alt)" : heatColor(t),
                            }}
                          />
                        );
                      })
                    )}
                  </div>
                  <div
                    className="mt-1.5 flex justify-between text-[10px] text-fg-faint"
                    style={{ width: bins * cellPx + (bins - 1) * 2 }}
                  >
                    <span>0.0</span>
                    <span>Perceived Significance (P)</span>
                    <span>1.0</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-[11px]">
                  <thead>
                    <tr>
                      <th className="px-2 py-1 text-left font-medium text-fg-faint">R \ P</th>
                      {colOrder.map((p) => (
                        <th key={p} className="px-2 py-1 text-right font-mono font-normal text-fg-faint">
                          {binLabel(p)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rowOrder.map((r) => (
                      <tr key={r} className="border-t border-line-soft">
                        <td className="px-2 py-1 font-mono text-fg-faint">{binLabel(r)}</td>
                        {colOrder.map((p) => (
                          <td key={p} className="px-2 py-1 text-right font-mono tabular-nums text-fg-dim">
                            {(cellByPos.get(`${p}-${r}`) ?? 0).toLocaleString()}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="mt-3.5 flex items-center gap-2 text-[10px] text-fg-faint">
              <span>Fewer</span>
              <div
                className="h-2 w-full max-w-[160px] rounded-full"
                style={{ background: `linear-gradient(to right, ${heatColor(0)}, ${heatColor(0.5)}, ${heatColor(1)})` }}
              />
              <span>More</span>
              <span className="ml-1">(log scale — a few cells otherwise dwarf the rest)</span>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}

function ThresholdNote({
  axis,
  label,
  threshold,
  compact = false,
}: {
  axis: "P" | "R";
  label: string;
  threshold: GroupThreshold;
  compact?: boolean;
}) {
  const color = axis === "P" ? "text-amber" : "text-violet-deep";
  if (threshold.threshold_score === null) {
    return <span className="text-[11px] text-fg-faint">{label} {axis}: not enough scored events yet</span>;
  }
  return (
    <span className="font-mono text-[11px] tabular-nums text-fg-faint">
      {!compact && `${label} ${axis} threshold: `}
      {axis} ≥ <span className={color}>{threshold.threshold_score.toFixed(3)}</span>
      {" "}
      (top {Math.round(threshold.top_percentile * 100)}% of {threshold.group_size.toLocaleString()})
    </span>
  );
}

function EventRow({ event, safeName, delay }: { event: EventSummary; safeName: string; delay: number }) {
  return (
    <Link href={`/repos/${safeName}/events/${event.id}`} className="block rise" style={{ animationDelay: `${delay}ms` }}>
      <Panel hover className="flex items-center justify-between gap-4 px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm text-fg">{event.title}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-fg-faint">
            <Badge tone={event.event_type}>{event.event_type.replace("_", " ")}</Badge>
            {event.p_score?.is_high_p && <Badge tone="high-p">high P</Badge>}
            {event.r_score?.is_high_r && <Badge tone="high-r">high R</Badge>}
            {event.divergence && <Badge tone={event.divergence.quadrant}>{QUADRANT_LABELS[event.divergence.quadrant]}</Badge>}
            {event.source_pr_number !== null && <span className="font-mono">#{event.source_pr_number}</span>}
            {event.primary_commit_hash && <span className="font-mono">{event.primary_commit_hash.slice(0, 8)}</span>}
            {event.author?.github_login && (
              <span>
                {event.author.github_login}
                {event.author.is_bot && <span className="ml-1 text-amber">bot</span>}
              </span>
            )}
          </div>
        </div>
        <span className="shrink-0 text-right text-[11px] tabular-nums">
          {event.p_score?.p_score !== null && event.p_score?.p_score !== undefined && (
            <div className={event.p_score.is_high_p ? "font-medium text-amber" : "text-fg-faint"}>P {event.p_score.p_score.toFixed(2)}</div>
          )}
          {event.r_score?.r_score !== null && event.r_score?.r_score !== undefined && (
            <div className={event.r_score.is_high_r ? "font-medium text-violet-deep" : "text-fg-faint"}>R {event.r_score.r_score.toFixed(2)}</div>
          )}
          <div className="text-fg-faint">{new Date(event.occurred_at).toLocaleDateString()}</div>
        </span>
      </Panel>
    </Link>
  );
}

function FilterLabel({ children }: { children: React.ReactNode }) {
  return <div className="mb-1.5 text-[10px] font-semibold tracking-[0.1em] text-fg-faint uppercase">{children}</div>;
}

function FilterSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full appearance-none rounded-lg border border-line bg-surface py-2 pl-3 pr-8 text-[13px] text-fg outline-none transition focus:border-indigo/50 focus:ring-2 focus:ring-indigo/15"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <svg viewBox="0 0 20 20" fill="none" className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-faint">
        <path d="M5 8l5 5 5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
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
    <div className="inline-flex rounded-lg border border-line bg-surface-alt p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-[6px] px-3 py-1.5 text-xs font-medium transition ${
            value === o.value ? "bg-indigo text-white shadow-sm" : "text-fg-dim hover:text-fg"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function PageButton({ disabled, onClick, children }: { disabled: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className="rounded-lg border border-line bg-surface px-3 py-1.5 text-xs text-fg-dim transition hover:border-indigo/30 hover:text-indigo disabled:opacity-30 disabled:hover:border-line disabled:hover:text-fg-dim"
    >
      {children}
    </button>
  );
}
