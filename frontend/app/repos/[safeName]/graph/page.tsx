"use client";

import cytoscape, { Core, ElementDefinition, NodeSingular } from "cytoscape";
import fcose from "cytoscape-fcose";
import Link from "next/link";
import { use, useEffect, useMemo, useRef, useState } from "react";
import { BackLink, Shell } from "../../../components/ui";
import { api, EventDetail, GraphNode, P_FEATURE_LABELS, Quadrant, QUADRANT_LABELS, R_FEATURE_LABELS, RepoGraph } from "../../../lib/api";

if (typeof cytoscape.prototype !== "undefined") {
  try {
    cytoscape.use(fcose);
  } catch {
    // already registered (hot reload / repeated mount) -- safe to ignore
  }
}

// Dark/neon theme, scoped to this page only -- deliberately distinct from
// the rest of the app's light design system, the way Neo4j's own Bloom/
// Browser tools use a dark canvas for graph exploration specifically.
// Hues are the same validated dark-mode-safe slots the rest of the app
// already uses (app/globals.css), chosen so quadrant identity (the actual
// HistSig data) stays colorblind-distinguishable -- "neon" comes from the
// near-black surface + saturated fills + a soft bloom filter on the
// canvas, not from pushing any hue outside its validated lightness band.
const SURFACE = "#0a0a0f";
const SURFACE_PANEL = "#111118";
const LINE = "#242433";
const TEXT_PRIMARY = "#f1f1f6";
const TEXT_DIM = "#9a9ab0";
const TEXT_FAINT = "#6b6b82";

const QUADRANT_COLOR: Record<string, string> = {
  truly_important: "#2bdb94",
  discussed_but_forgotten: "#ff8a3d",
  silent_but_critical: "#a78bfa",
  routine_noise: "#52525b",
};
const DEVELOPER_COLOR = "#3b82f6";
const FILE_COLOR = "#cbd5e1";
const HIGH_SCORE_GLOW = "#ffffff";

const TOP_N_ALWAYS_LABELED = 12;

type SizeMetric = "p_score" | "r_score";
type ViewMode = "graph" | "timeline" | "table";

const MAX_FILE_SATELLITES = 5;
const SNAKE_COL_WIDTH = 170;
const SNAKE_ROW_HEIGHT = 320;

type TimelineStrictness = "truly_important" | "major";

function isTimelineEvent(n: GraphNode, strictness: TimelineStrictness): boolean {
  if (n.type !== "HistoricalEvent") return false;
  if (strictness === "truly_important") return n.quadrant === "truly_important";
  return Boolean(n.is_high_p || n.is_high_r);
}

// A single winding path through the repo's history, ordered purely by
// time -- a "map route" rather than three parallel timelines. Quadrant
// color still marks each stop's category, but the trail itself is one
// connected sequence you can step through, which is the whole point: a
// repo's story read in order, not three disconnected strips of dots.
function toTimelineElements(
  graph: RepoGraph,
  sizeBy: SizeMetric,
  hiddenQuadrants: Set<string>,
  strictness: TimelineStrictness
): { elements: ElementDefinition[]; range: [string, string] | null; sortedIds: string[] } {
  const majorEvents = graph.nodes
    .filter((n) => isTimelineEvent(n, strictness))
    .filter((n) => n.occurred_at && n.quadrant && !hiddenQuadrants.has(n.quadrant));
  if (majorEvents.length === 0) return { elements: [], range: null, sortedIds: [] };

  const sorted = [...majorEvents].sort((a, b) => new Date(a.occurred_at!).getTime() - new Date(b.occurred_at!).getTime());

  // Real AUTHORED/MODIFIES edges already in the graph, indexed so each
  // shown event can pull in its *actual* developer and touched files --
  // not fabricated connections, the same evidence the force graph shows,
  // just scoped down to the curated event set instead of everything.
  const nodeById = new Map(graph.nodes.map((n) => [n.id, n]));
  const authorsByEvent = new Map<string, string[]>();
  const filesByEvent = new Map<string, string[]>();
  for (const e of graph.edges) {
    if (e.type === "AUTHORED") {
      if (!authorsByEvent.has(e.target)) authorsByEvent.set(e.target, []);
      authorsByEvent.get(e.target)!.push(e.source);
    } else if (e.type === "MODIFIES") {
      if (!filesByEvent.has(e.source)) filesByEvent.set(e.source, []);
      filesByEvent.get(e.source)!.push(e.target);
    }
  }

  // Roughly landscape-shaped grid so the route reads left-to-right in
  // readable rows instead of one impossibly wide strip.
  const itemsPerRow = Math.max(5, Math.ceil(Math.sqrt(sorted.length * 2.4)));

  const elements: ElementDefinition[] = [];
  const addedSatellites = new Set<string>();
  const positionById = new Map<string, { x: number; y: number }>();

  sorted.forEach((n, i) => {
    const row = Math.floor(i / itemsPerRow);
    const colInRow = i % itemsPerRow;
    const col = row % 2 === 0 ? colInRow : itemsPerRow - 1 - colInRow; // snake back on odd rows
    const x = 100 + col * SNAKE_COL_WIDTH;
    const y = 120 + row * SNAKE_ROW_HEIGHT;
    positionById.set(n.id, { x, y });

    const score = sizeBy === "p_score" ? n.p_score : n.r_score;
    const highlighted = sizeBy === "p_score" ? n.is_high_p : n.is_high_r;
    elements.push({
      data: {
        id: n.id, label: n.label, fullLabel: n.label, type: n.type, quadrant: n.quadrant,
        p_score: n.p_score ?? null, r_score: n.r_score ?? null, sizeValue: score ?? 0.3,
        highlighted: Boolean(highlighted), event_type: n.event_type ?? null, occurred_at: n.occurred_at,
        alwaysLabel: true, stepIndex: i,
      },
      position: { x, y },
    });

    // Developer satellite(s) just above the event.
    const authorIds = authorsByEvent.get(n.id) ?? [];
    authorIds.forEach((devId, di) => {
      const dev = nodeById.get(devId);
      if (!dev) return;
      if (!addedSatellites.has(devId)) {
        elements.push({
          data: { id: devId, label: dev.label, fullLabel: dev.label, type: "Developer", alwaysLabel: true },
          position: { x: x + di * 14, y: y - 46 },
          grabbable: false,
        });
        addedSatellites.add(devId);
      }
      elements.push({ data: { id: `sat-authored:${devId}->${n.id}`, source: devId, target: n.id, type: "AUTHORED" } });
    });

    // File satellites just below the event, capped so one huge PR can't
    // flood the view -- the full file list is still one click away via
    // the force graph or the event's own detail page.
    const fileIds = (filesByEvent.get(n.id) ?? []).slice(0, MAX_FILE_SATELLITES);
    fileIds.forEach((fileId, fi) => {
      const file = nodeById.get(fileId);
      if (!file) return;
      const satId = `${n.id}::${fileId}`; // files can repeat across events; satellite is per (event, file)
      if (!addedSatellites.has(satId)) {
        const spread = (fi - (fileIds.length - 1) / 2) * 16;
        elements.push({
          data: { id: satId, label: file.label.split("/").pop() ?? file.label, fullLabel: file.label, type: "File", alwaysLabel: true },
          position: { x: x + spread, y: y + 46 },
          grabbable: false,
        });
        addedSatellites.add(satId);
      }
      elements.push({ data: { id: `sat-modifies:${n.id}->${satId}`, source: n.id, target: satId, type: "MODIFIES" } });
    });
  });

  // The one continuous route -- this is the "map" itself. Still labeled
  // time-order only, not an asserted causal/derived relationship.
  for (let i = 1; i < sorted.length; i++) {
    elements.push({ data: { id: `seq:${sorted[i - 1].id}->${sorted[i].id}`, source: sorted[i - 1].id, target: sorted[i].id, type: "SEQUENCE" } });
  }

  return {
    elements,
    range: [sorted[0].occurred_at!, sorted[sorted.length - 1].occurred_at!],
    sortedIds: sorted.map((n) => n.id),
  };
}

function toElements(graph: RepoGraph, sizeBy: SizeMetric, alwaysLabelIds: Set<string>, hiddenQuadrants: Set<string>): ElementDefinition[] {
  const visibleIds = new Set<string>();
  const nodes: ElementDefinition[] = [];
  for (const n of graph.nodes) {
    if (n.type === "HistoricalEvent" && n.quadrant && hiddenQuadrants.has(n.quadrant)) continue;
    visibleIds.add(n.id);
    const score = sizeBy === "p_score" ? n.p_score : n.r_score;
    const highlighted = sizeBy === "p_score" ? n.is_high_p : n.is_high_r;
    nodes.push({
      data: {
        id: n.id,
        label: n.type === "File" ? n.label.split("/").pop() ?? n.label : n.label,
        fullLabel: n.label,
        type: n.type,
        quadrant: n.quadrant ?? null,
        p_score: n.p_score ?? null,
        r_score: n.r_score ?? null,
        sizeValue: score ?? 0.15,
        highlighted: Boolean(highlighted),
        event_type: n.event_type ?? null,
        occurred_at: n.occurred_at ?? null,
        is_bot: n.is_bot ?? null,
        alwaysLabel: alwaysLabelIds.has(n.id),
      },
    });
  }
  const edges: ElementDefinition[] = graph.edges
    .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
    .map((e) => ({ data: { id: e.id, source: e.source, target: e.target, type: e.type } }));
  return [...nodes, ...edges];
}

function GraphLegend({
  hiddenQuadrants,
  onToggle,
  nodeCount,
  edgeCount,
}: {
  hiddenQuadrants: Set<string>;
  onToggle: (q: Quadrant) => void;
  nodeCount: number;
  edgeCount: number;
}) {
  return (
    <div className="rounded-xl border px-4 py-3" style={{ background: SURFACE_PANEL, borderColor: LINE }}>
      <div className="text-[11px] font-semibold tracking-[0.14em] uppercase mb-2" style={{ color: TEXT_FAINT }}>
        Legend — click to toggle
      </div>
      <div className="space-y-1.5 text-xs">
        {(Object.entries(QUADRANT_LABELS) as [Quadrant, string][]).map(([q, label]) => {
          const hidden = hiddenQuadrants.has(q);
          return (
            <button
              key={q}
              onClick={() => onToggle(q)}
              className="flex items-center gap-2 w-full text-left transition-opacity"
              style={{ opacity: hidden ? 0.35 : 1 }}
            >
              <span
                className="inline-block w-2.5 h-2.5 rounded-full"
                style={{ background: QUADRANT_COLOR[q], boxShadow: hidden ? "none" : `0 0 6px ${QUADRANT_COLOR[q]}` }}
              />
              <span style={{ color: TEXT_DIM }}>{label}</span>
              {hidden && <span style={{ color: TEXT_FAINT }}>(hidden)</span>}
            </button>
          );
        })}
        <div className="flex items-center gap-2 pt-1">
          <span
            className="inline-block w-2.5 h-2.5"
            style={{ background: DEVELOPER_COLOR, clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)", boxShadow: `0 0 6px ${DEVELOPER_COLOR}` }}
          />
          <span style={{ color: TEXT_DIM }}>Developer</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-2.5 h-2.5" style={{ background: FILE_COLOR, clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" }} />
          <span style={{ color: TEXT_DIM }}>File</span>
        </div>
      </div>
      <div className="mt-3 pt-3 text-[11px]" style={{ borderTop: `1px solid ${LINE}`, color: TEXT_FAINT }}>
        {nodeCount.toLocaleString()} nodes · {edgeCount.toLocaleString()} edges
      </div>
    </div>
  );
}

function FeatureRow({ label, entry }: { label: string; entry: { value: number | boolean | null; status: string } }) {
  if (entry.status === "not_applicable") {
    return (
      <div className="flex items-center justify-between text-[11px] py-0.5">
        <span style={{ color: TEXT_FAINT }}>{label}</span>
        <span style={{ color: TEXT_FAINT }}>n/a</span>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between text-[11px] py-0.5">
      <span style={{ color: TEXT_FAINT }}>{label}</span>
      <span style={{ color: TEXT_DIM }}>
        {typeof entry.value === "boolean" ? (entry.value ? "yes" : "no") : entry.value ?? "—"}
        {entry.status === "incomplete_lower_bound" && <span style={{ color: "#ff8a3d" }}> (floor)</span>}
      </span>
    </div>
  );
}

function SelectedEventPanel({ safeName, detail, loading }: { safeName: string; detail: EventDetail | null; loading: boolean }) {
  if (loading) return <div style={{ color: TEXT_FAINT }} className="text-xs">Loading evidence…</div>;
  if (!detail) return null;
  const quadrant = detail.divergence?.quadrant;
  return (
    <div className="space-y-3">
      <div>
        <div className="text-[11px] uppercase tracking-wide flex items-center gap-2" style={{ color: TEXT_FAINT }}>
          <span>{detail.event_type.replace("_", " ")}</span>
          {detail.occurred_at && <span>· {new Date(detail.occurred_at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}</span>}
        </div>
        <div className="text-sm font-medium leading-snug" style={{ color: TEXT_PRIMARY }}>
          {detail.title}
        </div>
        {quadrant && (
          <div
            className="inline-block mt-1.5 rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide"
            style={{ background: `${QUADRANT_COLOR[quadrant]}22`, color: QUADRANT_COLOR[quadrant], border: `1px solid ${QUADRANT_COLOR[quadrant]}55` }}
          >
            {QUADRANT_LABELS[quadrant]}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg px-2.5 py-2" style={{ background: SURFACE, border: `1px solid ${LINE}` }}>
          <div className="text-[10px]" style={{ color: TEXT_FAINT }}>P score</div>
          <div className="text-base font-semibold tabular-nums" style={{ color: TEXT_PRIMARY }}>
            {detail.p_score?.p_score != null ? detail.p_score.p_score.toFixed(3) : "—"}
          </div>
        </div>
        <div className="rounded-lg px-2.5 py-2" style={{ background: SURFACE, border: `1px solid ${LINE}` }}>
          <div className="text-[10px]" style={{ color: TEXT_FAINT }}>R score</div>
          <div className="text-base font-semibold tabular-nums" style={{ color: TEXT_PRIMARY }}>
            {detail.r_score?.r_score != null ? detail.r_score.r_score.toFixed(3) : "—"}
          </div>
        </div>
      </div>

      {detail.p_features && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide mb-1" style={{ color: TEXT_FAINT }}>
            Why this P score — raw evidence
          </div>
          {Object.entries(detail.p_features).map(([name, entry]) => (
            <FeatureRow key={name} label={P_FEATURE_LABELS[name] ?? name} entry={entry} />
          ))}
        </div>
      )}

      {detail.r_features && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide mb-1" style={{ color: TEXT_FAINT }}>
            Why this R score — raw evidence
          </div>
          {detail.r_features.maturity.value != null && (
            <div className="text-[11px] py-0.5" style={{ color: TEXT_FAINT }}>
              Maturity: {Math.round(detail.r_features.maturity.value * 100)}%
              {detail.r_features.maturity.value < 0.05 ? " — too young to rank yet" : ""}
            </div>
          )}
          {Object.entries(detail.r_features.features).map(([name, entry]) => (
            <FeatureRow key={name} label={R_FEATURE_LABELS[name] ?? name} entry={entry} />
          ))}
        </div>
      )}

      <Link
        href={`/repos/${safeName}/events/${detail.id}`}
        className="inline-flex items-center gap-1 text-xs font-medium transition-colors"
        style={{ color: "#60a5fa" }}
      >
        Open full event page →
      </Link>
    </div>
  );
}

export default function RepoGraphPage({ params }: { params: Promise<{ safeName: string }> }) {
  const { safeName } = use(params);
  const [graph, setGraph] = useState<RepoGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyScored, setOnlyScored] = useState(true);
  const [sizeBy, setSizeBy] = useState<SizeMetric>("p_score");
  const [timelineStrict, setTimelineStrict] = useState<TimelineStrictness>("truly_important");
  const [tourIndex, setTourIndex] = useState<number | null>(null);
  const [hoverTip, setHoverTip] = useState<{ x: number; y: number; title: string; quadrant: Quadrant | null; date: string | null } | null>(null);
  const [hiddenQuadrants, setHiddenQuadrants] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [selectedType, setSelectedType] = useState<GraphNode["type"] | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string>("");
  const [eventDetail, setEventDetail] = useState<EventDetail | null>(null);
  const [eventDetailLoading, setEventDetailLoading] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const graphAreaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setGraph(null);
    setError(null);
    api
      .getRepoGraph(safeName, onlyScored)
      .then(setGraph)
      .catch((err) => setError(String(err)));
  }, [safeName, onlyScored]);

  const visibleCounts = useMemo(() => {
    if (!graph) return { nodes: 0, edges: 0 };
    const elements = toElements(graph, sizeBy, new Set(), hiddenQuadrants);
    return {
      nodes: elements.filter((e) => !("source" in e.data)).length,
      edges: elements.filter((e) => "source" in e.data).length,
    };
  }, [graph, sizeBy, hiddenQuadrants]);

  const alwaysLabelIds = useMemo(() => {
    if (!graph) return new Set<string>();
    const scored = graph.nodes
      .filter((n) => n.type === "HistoricalEvent" && (sizeBy === "p_score" ? n.p_score : n.r_score) != null)
      .sort((a, b) => ((sizeBy === "p_score" ? b.p_score : b.r_score) ?? 0) - ((sizeBy === "p_score" ? a.p_score : a.r_score) ?? 0))
      .slice(0, TOP_N_ALWAYS_LABELED);
    return new Set(scored.map((n) => n.id));
  }, [graph, sizeBy]);

  const timelineData = useMemo(
    () => (graph ? toTimelineElements(graph, sizeBy, hiddenQuadrants, timelineStrict) : { elements: [], range: null, sortedIds: [] }),
    [graph, sizeBy, hiddenQuadrants, timelineStrict]
  );

  useEffect(() => {
    if (!graph || !containerRef.current || (viewMode !== "graph" && viewMode !== "timeline")) return;
    const isTimeline = viewMode === "timeline";

    const cy = cytoscape({
      container: containerRef.current,
      elements: isTimeline ? timelineData.elements : toElements(graph, sizeBy, alwaysLabelIds, hiddenQuadrants),
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "font-size": 8,
            color: TEXT_DIM,
            "text-valign": "bottom",
            "text-margin-y": 5,
            "text-max-width": "90px",
            "text-wrap": "ellipsis",
            "text-opacity": 0,
            "min-zoomed-font-size": 7,
            "border-width": 1.5,
            "border-color": SURFACE,
          } as never,
        },
        { selector: "node.always-label, node:selected, node.hovered, node.neighbor", style: { "text-opacity": 1 } },
        {
          selector: "node[type = 'HistoricalEvent']",
          style: {
            "background-color": (ele: NodeSingular) => QUADRANT_COLOR[ele.data("quadrant")] ?? "#3f3f52",
            width: "mapData(sizeValue, 0, 1, 8, 34)",
            height: "mapData(sizeValue, 0, 1, 8, 34)",
          } as never,
        },
        {
          selector: "node[type = 'HistoricalEvent'][?highlighted]",
          style: { "border-width": 3, "border-color": HIGH_SCORE_GLOW, "border-opacity": 0.55 },
        },
        {
          selector: "node[type = 'Developer']",
          style: { "background-color": DEVELOPER_COLOR, shape: "triangle", width: 13, height: 13 },
        },
        {
          selector: "node[type = 'File']",
          style: { "background-color": FILE_COLOR, shape: "diamond", width: 9, height: 9 },
        },
        {
          selector: "node:selected",
          style: { "border-width": 3, "border-color": "#ffffff", "border-opacity": 1 },
        },
        {
          selector: "node.dimmed",
          style: { opacity: 0.12 },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": LINE,
            "curve-style": "haystack",
            "haystack-radius": 0,
            "target-arrow-shape": "none",
            opacity: 0.6,
          },
        },
        { selector: "edge[type = 'AUTHORED']", style: { "line-color": "#2d3a5c", "line-style": "dashed" } },
        { selector: "edge[type = 'MODIFIES']", style: { "line-color": "#2a2a3d" } },
        { selector: "edge.dimmed", style: { opacity: 0.04 } },
        { selector: "edge.highlighted", style: { "line-color": "#60a5fa", opacity: 1, width: 1.6 } },
        {
          // The route itself -- a visible "road" with direction arrows so
          // the path reads as a journey through time, not just a generic
          // connection. Curved (not straight) so the snake-back at the end
          // of each row looks like a bend in the road, not a glitch.
          selector: "edge[type = 'SEQUENCE']",
          style: {
            "line-color": "#4b4b6b", width: 2, "curve-style": "bezier", opacity: 0.55,
            "target-arrow-shape": "triangle", "target-arrow-color": "#4b4b6b", "arrow-scale": 0.8,
          },
        },
        { selector: "edge[type = 'SEQUENCE'].highlighted", style: { "line-color": "#60a5fa", "target-arrow-color": "#60a5fa", opacity: 1, width: 2.5 } },
      ],
      layout: isTimeline
        ? { name: "preset", fit: true, padding: 40 }
        : ({ name: "fcose", animate: false, nodeRepulsion: 6000, idealEdgeLength: 45, nodeSeparation: 40 } as never),
      wheelSensitivity: 1,
      minZoom: 0.05,
      maxZoom: 8,
      selectionType: "single",
      // Nodes were individually draggable by default, which meant a drag
      // gesture that happened to start on a node (easy to hit once zoomed
      // in, since nodes cover more screen area) moved *that node* instead
      // of panning the canvas -- this is almost certainly what felt like
      // "can't move to other nodes once zoomed in." This is a read-only
      // explorer, not a diagram editor, so elements should never be
      // draggable; every mousedown-drag now pans the canvas instead.
      autoungrabify: true,
    });

    cy.elements().forEach((ele) => {
      if (ele.isNode() && ele.data("alwaysLabel")) ele.addClass("always-label");
    });

    cy.on("mouseover", "node", (evt) => {
      const node = evt.target as NodeSingular;
      const neighborhood = node.closedNeighborhood();
      cy.elements().addClass("dimmed");
      neighborhood.removeClass("dimmed");
      node.addClass("hovered");
      neighborhood.edges().addClass("highlighted");
      neighborhood.nodes().addClass("neighbor");

      // Quick-scan preview -- title/quadrant/date without committing to a
      // click, the same "hover a pin to see what it is" pattern a map uses.
      if (node.data("type") === "HistoricalEvent") {
        const pos = node.renderedPosition();
        const containerRect = containerRef.current?.getBoundingClientRect();
        if (containerRect) {
          setHoverTip({
            x: containerRect.left + pos.x,
            y: containerRect.top + pos.y,
            title: node.data("fullLabel"),
            quadrant: node.data("quadrant"),
            date: node.data("occurred_at"),
          });
        }
      }
    });
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("dimmed hovered neighbor highlighted");
      setHoverTip(null);
    });
    cy.on("pan zoom", () => setHoverTip(null));

    cy.on("tap", "node", (evt) => {
      const d = evt.target.data();
      if (d.type === "LaneLabel" || d.type === "DateTick") return;
      setSelectedType(d.type);
      setSelectedLabel(d.fullLabel);
      if (d.type === "HistoricalEvent") {
        const eventId = Number(String(d.id).replace("event:", ""));
        setSelectedEventId(eventId);
      } else {
        setSelectedEventId(null);
        setEventDetail(null);
      }
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        setSelectedType(null);
        setSelectedEventId(null);
        setEventDetail(null);
      }
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [graph, sizeBy, hiddenQuadrants, alwaysLabelIds, viewMode, timelineData]);

  // The tour position is an index into timelineData.sortedIds -- reset it
  // whenever that list could have changed shape (different filter,
  // different strictness, leaving timeline mode) so Next/Previous can't
  // silently jump to an unrelated event after the underlying list shifts.
  useEffect(() => {
    setTourIndex(null);
  }, [viewMode, timelineStrict, hiddenQuadrants]);

  useEffect(() => {
    if (selectedEventId == null) return;
    setEventDetailLoading(true);
    setEventDetail(null);
    api
      .getEvent(safeName, selectedEventId)
      .then(setEventDetail)
      .catch(() => setEventDetail(null))
      .finally(() => setEventDetailLoading(false));
  }, [safeName, selectedEventId]);

  useEffect(() => {
    const onChange = () => {
      const active = document.fullscreenElement === graphAreaRef.current;
      setIsFullscreen(active);
      requestAnimationFrame(() => {
        cyRef.current?.resize();
        cyRef.current?.fit(undefined, 30);
      });
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else graphAreaRef.current?.requestFullscreen();
  }
  function toggleQuadrant(q: Quadrant) {
    setHiddenQuadrants((prev) => {
      const next = new Set(prev);
      if (next.has(q)) next.delete(q);
      else next.add(q);
      return next;
    });
  }
  function fitToView() {
    cyRef.current?.fit(undefined, 30);
  }
  function zoomBy(factor: number) {
    const cy = cyRef.current;
    if (!cy) return;
    // Zoom centered on the current viewport center, same as clicking a
    // website's own +/- controls (vs. wheel-zoom, which centers on the
    // cursor) -- predictable regardless of where the pointer happens to be.
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }

  // Guided-tour step: selects the event (same rich panel as a manual
  // click) and animates the camera to center on it -- a literal walk
  // through the repo's history in order, not just free exploration.
  function goToStep(index: number) {
    const ids = timelineData.sortedIds;
    if (index < 0 || index >= ids.length) return;
    setTourIndex(index);
    const id = ids[index];
    setSelectedType("HistoricalEvent");
    setSelectedEventId(Number(id.replace("event:", "")));
    const cy = cyRef.current;
    const ele = cy?.getElementById(id);
    if (cy && ele && ele.length > 0) {
      cy.animate({ fit: { eles: ele.closedNeighborhood(), padding: 160 } }, { duration: 450 });
      cy.elements().removeClass("dimmed hovered neighbor highlighted");
      cy.elements().addClass("dimmed");
      ele.closedNeighborhood().removeClass("dimmed");
      ele.closedNeighborhood().edges().addClass("highlighted");
    }
  }

  return (
    <Shell width="max-w-6xl">
      <BackLink href={`/repos/${safeName}`}>{safeName.replace("__", "/")}</BackLink>

      <div className="mt-3 flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Knowledge graph</h1>
        <div className="flex items-center gap-3 flex-wrap text-xs">
          <label className="flex items-center gap-2 text-fg-faint">
            <input type="checkbox" checked={onlyScored} onChange={(e) => setOnlyScored(e.target.checked)} />
            Only scored events
          </label>
          <label className="flex items-center gap-2 text-fg-faint">
            Size by
            <select
              value={sizeBy}
              onChange={(e) => setSizeBy(e.target.value as SizeMetric)}
              className="rounded border border-line bg-surface px-1.5 py-1 text-xs"
            >
              <option value="p_score">P score</option>
              <option value="r_score">R score</option>
            </select>
          </label>
          {viewMode === "timeline" && (
            <label className="flex items-center gap-2 text-fg-faint">
              Show
              <select
                value={timelineStrict}
                onChange={(e) => setTimelineStrict(e.target.value as TimelineStrictness)}
                className="rounded border border-line bg-surface px-1.5 py-1 text-xs"
              >
                <option value="truly_important">Truly important only</option>
                <option value="major">Major (P or R high)</option>
              </select>
            </label>
          )}
          <div className="flex rounded-lg border border-line overflow-hidden">
            {(["graph", "timeline", "table"] as ViewMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setViewMode(m)}
                className={`px-3 py-1.5 font-medium transition ${
                  viewMode === m ? "bg-indigo text-white" : "bg-surface text-fg-dim hover:text-indigo"
                }`}
              >
                {m === "graph" ? "Force graph" : m === "timeline" ? "Timeline" : "Table"}
              </button>
            ))}
          </div>
          {graph && (viewMode === "graph" || viewMode === "timeline") && (
            <>
              <div className="flex rounded-lg border border-line overflow-hidden">
                <button
                  onClick={() => zoomBy(1 / 1.4)}
                  aria-label="Zoom out"
                  className="px-3 py-1.5 font-medium bg-surface text-fg-dim hover:text-indigo transition border-r border-line"
                >
                  −
                </button>
                <button
                  onClick={() => zoomBy(1.4)}
                  aria-label="Zoom in"
                  className="px-3 py-1.5 font-medium bg-surface text-fg-dim hover:text-indigo transition"
                >
                  +
                </button>
              </div>
              <button
                onClick={fitToView}
                className="rounded-lg border border-line bg-surface px-3 py-1.5 font-medium text-fg-dim hover:border-indigo/30 hover:text-indigo transition"
              >
                Fit to view
              </button>
              <button
                onClick={toggleFullscreen}
                className="rounded-lg border border-line bg-surface px-3 py-1.5 font-medium text-fg-dim hover:border-indigo/30 hover:text-indigo transition"
              >
                {isFullscreen ? "Exit fullscreen" : "Fullscreen"}
              </button>
            </>
          )}
        </div>
      </div>
      <p className="mt-1.5 text-xs text-fg-faint max-w-2xl">
        {viewMode === "timeline" ? (
          <>
            {timelineStrict === "truly_important"
              ? "Only Truly Important events — high on both axes, HistSig's strongest signal — "
              : "Events flagged high-P or high-R — stood out on at least one axis — "}
            one connected route through the repo's history in date order, color-coded by quadrant, each stop with
            its real author and the files it touched. The arrowed line is time-order only; it does not claim one
            event caused or relates to the next. Use Previous/Next to step through it in order.
            {timelineData.range && (
              <>
                {" "}Spans {new Date(timelineData.range[0]).toLocaleDateString()} – {new Date(timelineData.range[1]).toLocaleDateString()}
                , {timelineData.sortedIds.length} events.
              </>
            )}
          </>
        ) : (
          <>
            Iteration 1 — Developer, HistoricalEvent, and File nodes, read live from Neo4j. Not the full ontology yet
            (no Issue/PullRequest/Review/Release nodes). Node size reflects the selected score; the bright ring marks
            events flagged high on that axis. Hover a node to see its immediate neighborhood.
          </>
        )}
      </p>

      {viewMode === "timeline" && timelineData.sortedIds.length > 0 && (
        <div className="mt-3 flex items-center gap-3 rounded-lg px-3 py-2" style={{ background: SURFACE_PANEL, border: `1px solid ${LINE}` }}>
          <button
            onClick={() => goToStep((tourIndex ?? 0) - 1)}
            disabled={tourIndex === null || tourIndex <= 0}
            className="rounded-md border border-line bg-surface px-3 py-1 text-xs font-medium text-fg-dim hover:text-indigo transition disabled:opacity-30 disabled:hover:text-fg-dim"
          >
            ← Previous
          </button>
          <span className="text-xs tabular-nums" style={{ color: TEXT_FAINT }}>
            {tourIndex === null ? `Guided tour — ${timelineData.sortedIds.length} stops` : `Stop ${tourIndex + 1} of ${timelineData.sortedIds.length}`}
          </span>
          <button
            onClick={() => goToStep((tourIndex ?? -1) + 1)}
            disabled={tourIndex !== null && tourIndex >= timelineData.sortedIds.length - 1}
            className="rounded-md border border-line bg-indigo px-3 py-1 text-xs font-medium text-white transition disabled:opacity-30"
          >
            {tourIndex === null ? "Start tour →" : "Next →"}
          </button>
        </div>
      )}

      {error && <div className="mt-6 rounded-xl px-4 py-3 text-sm text-red-400" style={{ background: SURFACE_PANEL, border: `1px solid ${LINE}` }}>{error}</div>}
      {!error && graph === null && <div className="mt-6 panel sheen h-[70vh]" />}

      {graph && viewMode === "table" && (
        <div className="mt-6 overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-fg-faint border-b border-line">
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Label</th>
                <th className="px-3 py-2">Quadrant</th>
                <th className="px-3 py-2">P score</th>
                <th className="px-3 py-2">R score</th>
              </tr>
            </thead>
            <tbody>
              {graph.nodes.map((n) => (
                <tr key={n.id} className="border-b border-line-soft">
                  <td className="px-3 py-1.5 text-fg-faint">{n.type}</td>
                  <td className="px-3 py-1.5 text-fg">{n.label}</td>
                  <td className="px-3 py-1.5 text-fg-dim">{n.quadrant ? QUADRANT_LABELS[n.quadrant] : "—"}</td>
                  <td className="px-3 py-1.5 tabular-nums text-fg-dim">{n.p_score != null ? n.p_score.toFixed(3) : "—"}</td>
                  <td className="px-3 py-1.5 tabular-nums text-fg-dim">{n.r_score != null ? n.r_score.toFixed(3) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {graph && (viewMode === "graph" || viewMode === "timeline") && (
        <div
          ref={graphAreaRef}
          className={isFullscreen ? "p-4 grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4 w-screen h-screen" : "mt-6 grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4"}
          style={{ background: isFullscreen ? SURFACE : "transparent" }}
        >
          <div className="rounded-xl overflow-hidden" style={{ background: SURFACE, border: `1px solid ${LINE}`, filter: "drop-shadow(0 0 14px rgba(99,102,241,0.08))" }}>
            <div ref={containerRef} style={{ width: "100%", height: isFullscreen ? "calc(100vh - 32px)" : "70vh" }} />
          </div>

          <div className={`space-y-4 ${isFullscreen ? "overflow-y-auto" : ""}`}>
            <GraphLegend
              hiddenQuadrants={hiddenQuadrants}
              onToggle={toggleQuadrant}
              nodeCount={viewMode === "timeline" ? timelineData.elements.filter((e) => !("source" in e.data)).length : visibleCounts.nodes}
              edgeCount={viewMode === "timeline" ? timelineData.elements.filter((e) => "source" in e.data).length : visibleCounts.edges}
            />

            <div className="rounded-xl px-4 py-3" style={{ background: SURFACE_PANEL, border: `1px solid ${LINE}` }}>
              <div className="text-[11px] font-semibold tracking-[0.14em] uppercase mb-2" style={{ color: TEXT_FAINT }}>
                Selected node
              </div>
              {!selectedType && <p className="text-xs" style={{ color: TEXT_FAINT }}>Click a node to inspect it.</p>}
              {selectedType && selectedType !== "HistoricalEvent" && (
                <div className="text-xs">
                  <div style={{ color: TEXT_FAINT }} className="uppercase tracking-wide text-[10px]">{selectedType}</div>
                  <div style={{ color: TEXT_PRIMARY }} className="font-medium mt-0.5">{selectedLabel}</div>
                </div>
              )}
              {selectedType === "HistoricalEvent" && (
                <SelectedEventPanel safeName={safeName} detail={eventDetail} loading={eventDetailLoading} />
              )}
            </div>
          </div>
        </div>
      )}

      {hoverTip && (
        <div
          className="fixed z-50 pointer-events-none rounded-lg px-3 py-2 text-xs max-w-[240px]"
          style={{ left: hoverTip.x + 16, top: hoverTip.y - 10, background: "#000000e6", border: `1px solid ${LINE}`, color: TEXT_PRIMARY }}
        >
          <div className="font-medium leading-snug">{hoverTip.title}</div>
          <div className="mt-1 flex items-center gap-1.5" style={{ color: TEXT_FAINT }}>
            {hoverTip.quadrant && (
              <span className="inline-block w-2 h-2 rounded-full" style={{ background: QUADRANT_COLOR[hoverTip.quadrant] }} />
            )}
            {hoverTip.quadrant && QUADRANT_LABELS[hoverTip.quadrant]}
            {hoverTip.date && <span>· {new Date(hoverTip.date).toLocaleDateString()}</span>}
          </div>
        </div>
      )}
    </Shell>
  );
}
