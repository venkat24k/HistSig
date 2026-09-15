"""P-score and R-score schema (Phase 3).

Four tables, structurally parallel but kept fully separate per axis (P
and R must never be collapsed together — CLAUDE.md Section 2/25):

- `event_p_scores` / `event_r_scores`: one row per event with its
  composite score (NULL when the event had zero applicable features to
  score from) and whether it cleared the "high attention"/"high salience"
  threshold for its group.
- `p_score_thresholds` / `r_score_thresholds`: one row per
  (granularity, event_type) group, recording exactly what threshold was
  used and how large the group was — the threshold is a parameter, not a
  hard-coded constant (see CLAUDE.md Section 25), and reproducibility
  requires it be documented alongside the results it produced (Section
  13), not just implied.
"""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_p_scores (
    event_id       INTEGER PRIMARY KEY REFERENCES candidate_events(id) ON DELETE CASCADE,
    repo_id        INTEGER NOT NULL,
    granularity    TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    p_score        REAL,
    features_used  INTEGER NOT NULL,
    is_high_p      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_event_p_scores_group
    ON event_p_scores(repo_id, granularity, event_type);

CREATE TABLE IF NOT EXISTS p_score_thresholds (
    repo_id          INTEGER NOT NULL,
    granularity      TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    top_percentile   REAL NOT NULL,
    threshold_score  REAL,
    group_size       INTEGER NOT NULL,
    PRIMARY KEY (repo_id, granularity, event_type)
);
"""

R_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_r_scores (
    event_id       INTEGER PRIMARY KEY REFERENCES candidate_events(id) ON DELETE CASCADE,
    repo_id        INTEGER NOT NULL,
    granularity    TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    r_score        REAL,
    features_used  INTEGER NOT NULL,
    is_high_r      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_event_r_scores_group
    ON event_r_scores(repo_id, granularity, event_type);

CREATE TABLE IF NOT EXISTS r_score_thresholds (
    repo_id          INTEGER NOT NULL,
    granularity      TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    top_percentile   REAL NOT NULL,
    threshold_score  REAL,
    group_size       INTEGER NOT NULL,
    PRIMARY KEY (repo_id, granularity, event_type)
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def reset_schema(conn: sqlite3.Connection) -> None:
    """Drop and recreate both P-score tables, then re-run create_schema.

    Same reasoning as src/features/schema.py's reset_schema: scoring is
    always fully regenerated per repo on each run, nothing else
    references these tables, and `CREATE TABLE IF NOT EXISTS` can't add a
    column to a table that already exists — so a plain create_schema call
    would leave a stale schema behind if this table's shape changes later.
    """
    conn.execute("DROP TABLE IF EXISTS event_p_scores")
    conn.execute("DROP TABLE IF EXISTS p_score_thresholds")
    conn.commit()
    create_schema(conn)


def create_r_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(R_SCHEMA_SQL)
    conn.commit()


def reset_r_schema(conn: sqlite3.Connection) -> None:
    """Same reasoning as reset_schema, kept separate so re-running P
    scoring never wipes already-computed R scores and vice versa."""
    conn.execute("DROP TABLE IF EXISTS event_r_scores")
    conn.execute("DROP TABLE IF EXISTS r_score_thresholds")
    conn.commit()
    create_r_schema(conn)
