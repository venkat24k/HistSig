"""Shared percentile-rank scoring core for both P and R (see p_score.py /
r_score.py). The algorithm — percentile-rank average per
`(granularity, event_type)` group, then a top-percentile threshold — is
identical for both axes; only the feature table and feature names differ.
Kept as its own module rather than folded into either p_score.py or
r_score.py, so neither axis's file claims ownership of logic the other
equally depends on — P and R must stay structurally separate (CLAUDE.md
Section 2/25).

Method (agreed with the user for P before implementing, since a scoring
formula/threshold is exactly the kind of methodology decision CLAUDE.md
Section 25 reserves for explicit approval, not something to pick
unilaterally; reused as-is for R at the user's explicit request to "do
everything we did for P" for R too):

1. Events are grouped by (granularity, event_type) before scoring, never
   scored across the whole repo at once. A standalone commit can only
   ever draw on a subset of the applicable features — it structurally has
   no comment/review channel for P, for instance — so comparing it to
   pull requests on one shared scale would make "high" almost always mean
   "was a PR," burying exactly the "silent but critical" events this
   research wants to be able to find.
2. Within a group, each feature is converted to a percentile rank in
   [0, 1] (`percentile_ranks`) rather than min-max or z-score scaled —
   robust to wildly different scales and heavy skew across features
   without an arbitrary log-transform decision.
3. An event's score is the *equal-weighted mean of only the percentile
   ranks that apply to it* (CLAUDE.md Section 34's settled equal-weighting
   decision). A `not_applicable` feature is excluded entirely, never
   averaged in as 0 — Section 20 explicitly forbids conflating those.
   `incomplete_lower_bound` values are used as-is: they're real, floor
   values, not missing data.
4. Within each group, the top `top_percentile` fraction of events by score
   are flagged "high" — an explicit, configurable parameter (never
   hard-coded, per Section 25), defaulting to 0.10 ("top 10%"). This is an
   exploratory first-pass cut, not a validated boundary — Section 11's
   evaluation stage is what would eventually check it against human
   judgment.
"""

import sqlite3
from collections import defaultdict

DEFAULT_TOP_PERCENTILE = 0.10


def percentile_ranks(values: list[tuple[int, float]]) -> dict[int, float]:
    """`values` is [(event_id, value), ...] for one feature within one
    scoring group. Returns {event_id: percentile_rank in [0, 1]}.

    Ties share the average rank of the positions they occupy (standard
    fractional ranking) rather than an arbitrary tie-break order. A group
    of exactly one event gets 0.5 (neutral) rather than a spurious 0 or 1
    — there's nothing to be "more/less than" with nothing else in the
    group to compare against.
    """
    n = len(values)
    if n == 0:
        return {}
    if n == 1:
        return {values[0][0]: 0.5}

    sorted_vals = sorted(v for _, v in values)
    positions: dict[float, list[int]] = defaultdict(list)
    for i, v in enumerate(sorted_vals, start=1):
        positions[v].append(i)
    avg_rank = {v: sum(ps) / len(ps) for v, ps in positions.items()}

    return {event_id: (avg_rank[value] - 0.5) / n for event_id, value in values}


def compute_group_scores(
    processed_conn: sqlite3.Connection,
    repo_id: int,
    feature_table: str,
    feature_names: tuple[str, ...],
    top_percentile: float = DEFAULT_TOP_PERCENTILE,
    exclude_event_ids: set[int] | None = None,
) -> dict:
    """Computes and returns (event_id -> score row) data for every event of
    `repo_id`, reading `feature_names`' value/status columns from
    `feature_table` (always one of this codebase's own two feature tables
    — never a caller-supplied value, so the f-string interpolation below
    is safe the same way every other internal-only table name in this
    codebase is). Callers persist the result via src/scoring/storage.py;
    the summary dict is for CLI/API reporting.

    `exclude_event_ids` (currently used only by R, for events below the
    minimum maturity to score/rank — see r_score.py) removes those events
    from the ranking population entirely: they never affect the
    percentile ranks or threshold computed for the events that *are*
    ranked, and their own group_size doesn't count them. They still get a
    row in `score_rows`, with `score=None`/`is_high=None` (excluded from
    ranking, not "computed as ineligible" the way zero-applicable-features
    is) — never silently dropped from the output. This is a different
    exclusion from `not_applicable` features: a feature can be
    inapplicable to an event that's still eligible to be ranked on its
    other features, while an excluded *event* never enters any group's
    ranking at all."""
    if not (0 < top_percentile <= 1):
        raise ValueError(f"top_percentile must be in (0, 1], got {top_percentile}")
    exclude_event_ids = exclude_event_ids or set()

    columns = ", ".join(f"{name}, {name}_status" for name in feature_names)
    rows = processed_conn.execute(
        f"""
        SELECT f.event_id, e.granularity, e.event_type, {columns}
        FROM {feature_table} f
        JOIN candidate_events e ON e.id = f.event_id
        WHERE f.repo_id = ?
        """,
        (repo_id,),
    ).fetchall()

    groups: dict[tuple[str, str], list[tuple[int, dict[str, float]]]] = defaultdict(list)
    excluded_rows: list[tuple[int, str, str, int]] = []
    for row in rows:
        event_id, granularity, event_type = row[0], row[1], row[2]
        applicable: dict[str, float] = {}
        for i, name in enumerate(feature_names):
            value, status = row[3 + 2 * i], row[3 + 2 * i + 1]
            if status != "not_applicable":
                applicable[name] = value
        if event_id in exclude_event_ids:
            excluded_rows.append((event_id, granularity, event_type, len(applicable)))
        else:
            groups[(granularity, event_type)].append((event_id, applicable))

    score_rows = []
    threshold_rows = []
    for (granularity, event_type), events in groups.items():
        per_feature_ranks = {
            name: percentile_ranks([(eid, fv[name]) for eid, fv in events if name in fv])
            for name in feature_names
        }

        scores: dict[int, float | None] = {}
        features_used: dict[int, int] = {}
        for event_id, fv in events:
            ranks = [per_feature_ranks[name][event_id] for name in fv]
            scores[event_id] = (sum(ranks) / len(ranks)) if ranks else None
            features_used[event_id] = len(ranks)

        non_null = sorted(v for v in scores.values() if v is not None)
        n = len(non_null)
        if n == 0:
            threshold_score = None
        else:
            top_k = max(1, round(n * top_percentile))
            threshold_score = non_null[n - top_k]

        for event_id, _ in events:
            score = scores[event_id]
            is_high = None if score is None or threshold_score is None else int(score >= threshold_score)
            score_rows.append((event_id, repo_id, granularity, event_type, score, features_used[event_id], is_high))

        threshold_rows.append((repo_id, granularity, event_type, top_percentile, threshold_score, n))

    for event_id, granularity, event_type, feature_count in excluded_rows:
        score_rows.append((event_id, repo_id, granularity, event_type, None, feature_count, None))

    summary = {
        "events_scored": len(score_rows),
        "events_with_no_applicable_features": sum(1 for r in score_rows if r[4] is None and r[0] not in exclude_event_ids),
        "events_excluded_from_ranking": len(excluded_rows),
        "top_percentile": top_percentile,
        "groups": [
            {"granularity": g, "event_type": et, "group_size": size, "threshold_score": thr}
            for _, g, et, _, thr, size in threshold_rows
        ],
    }
    return {"score_rows": score_rows, "threshold_rows": threshold_rows, "summary": summary}
