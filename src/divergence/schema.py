"""Divergence classification schema (Phase 4).

One row per event that has been scored on *both* P and R axes,
classifying it into one of CLAUDE.md Section 3's four quadrants
(`truly_important` / `discussed_but_forgotten` / `silent_but_critical` /
`routine_noise`). `p_score`/`r_score` are duplicated here from
`event_p_scores`/`event_r_scores` purely for provenance convenience
(CLAUDE.md Section 24) — so "why is this event in this quadrant" is
answerable directly from this table without a join back to Phase 3's own
tables.
"""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_divergence (
    event_id     INTEGER PRIMARY KEY REFERENCES candidate_events(id) ON DELETE CASCADE,
    repo_id      INTEGER NOT NULL,
    granularity  TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    p_score      REAL NOT NULL,
    r_score      REAL NOT NULL,
    is_high_p    INTEGER NOT NULL,
    is_high_r    INTEGER NOT NULL,
    quadrant     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_divergence_group ON event_divergence(repo_id, granularity, event_type);
CREATE INDEX IF NOT EXISTS idx_event_divergence_quadrant ON event_divergence(repo_id, quadrant);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def reset_schema(conn: sqlite3.Connection) -> None:
    """Same reasoning as the P/R feature and scoring schemas: divergence
    classification is always fully regenerated per repo on each run, and
    `CREATE TABLE IF NOT EXISTS` can't add a column to a table that
    already exists."""
    conn.execute("DROP TABLE IF EXISTS event_divergence")
    conn.commit()
    create_schema(conn)
