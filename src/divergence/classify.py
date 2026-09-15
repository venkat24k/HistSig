"""Divergence analysis (Phase 4): classify each fully-scored event into
one of CLAUDE.md Section 3's four P/R quadrants — the categories were
already defined and approved there (High P/High R = "Truly Important",
High P/Low R = "Discussed but Forgotten", Low P/High R = "Silent but
Critical", Low P/Low R = "Routine Noise"); nothing new is being invented
here (CLAUDE.md Section 25). "High"/"Low" reuses the `is_high_p`/
`is_high_r` flags Phase 3 scoring already computed (top-`top_percentile`
per `(granularity, event_type)` group — see `src/scoring/ranking.py`), so
no separate divergence-specific threshold is introduced either.

Only events where *both* axes were actually scored (`is_high_p` and
`is_high_r` are both non-NULL) are classified. An event missing either
axis — no applicable P or R features, that axis's Phase 3 run hasn't
happened yet for this repo, or (R-specific) excluded from ranking as too
young via `MIN_MATURITY_FOR_SCORING` — is left out of divergence entirely
rather than guessed at, per the missing-data principle used throughout
this project (CLAUDE.md Section 20): "we don't know its P or R" and "it's
Low" are not the same claim, so only genuinely known P/R pairs get a
quadrant label.
"""

import sqlite3

# CLAUDE.md Section 3's table, keyed by (is_high_p, is_high_r) as stored
# (SQLite INTEGER 0/1) — every quadrant this project recognizes.
QUADRANTS = {
    (1, 1): "truly_important",
    (1, 0): "discussed_but_forgotten",
    (0, 1): "silent_but_critical",
    (0, 0): "routine_noise",
}


def classify_divergence(processed_conn: sqlite3.Connection, repo_id: int) -> dict:
    rows = processed_conn.execute(
        """
        SELECT ps.event_id, ps.granularity, ps.event_type, ps.p_score, rs.r_score, ps.is_high_p, rs.is_high_r
        FROM event_p_scores ps
        JOIN event_r_scores rs ON rs.event_id = ps.event_id
        WHERE ps.repo_id = ? AND rs.repo_id = ?
          AND ps.is_high_p IS NOT NULL AND rs.is_high_r IS NOT NULL
        """,
        (repo_id, repo_id),
    ).fetchall()

    result_rows = [
        {
            "event_id": event_id,
            "granularity": granularity,
            "event_type": event_type,
            "p_score": p_score,
            "r_score": r_score,
            "is_high_p": is_high_p,
            "is_high_r": is_high_r,
            "quadrant": QUADRANTS[(is_high_p, is_high_r)],
        }
        for event_id, granularity, event_type, p_score, r_score, is_high_p, is_high_r in rows
    ]

    events_with_p_score = processed_conn.execute(
        "SELECT COUNT(*) FROM event_p_scores WHERE repo_id = ? AND is_high_p IS NOT NULL", (repo_id,)
    ).fetchone()[0]
    events_with_r_score = processed_conn.execute(
        "SELECT COUNT(*) FROM event_r_scores WHERE repo_id = ? AND is_high_r IS NOT NULL", (repo_id,)
    ).fetchone()[0]

    quadrant_counts: dict[str, int] = {label: 0 for label in QUADRANTS.values()}
    for r in result_rows:
        quadrant_counts[r["quadrant"]] += 1

    summary = {
        "events_classified": len(result_rows),
        "events_with_p_score": events_with_p_score,
        "events_with_r_score": events_with_r_score,
        "quadrant_counts": quadrant_counts,
    }
    return {"rows": result_rows, "summary": summary}
