"""P/R feature schema (Phase 2, second half).

Every feature gets a value column *and* a status column
('complete' | 'incomplete_lower_bound' | 'not_applicable') — never just a
number. A bare NULL or 0 can't distinguish "genuinely zero," "this
concept doesn't apply to this event type," and "we know a real value
exists but our collection was capped before we saw all of it" (see
CLAUDE.md Section 20). Values are computed feature-by-feature, verified
against real data, and added as their own column — not all at once.

P and R live in separate tables (`event_p_features` / `event_r_features`)
even though both follow the identical value+status pattern — P and R must
stay conceptually distinct (CLAUDE.md Section 2/25), and a single shared
table would blur that distinction in storage even if never in analysis.
"""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_p_features (
    event_id              INTEGER PRIMARY KEY REFERENCES candidate_events(id) ON DELETE CASCADE,
    repo_id                INTEGER NOT NULL,

    comment_count            INTEGER,
    comment_count_status     TEXT NOT NULL,

    distinct_commenters        INTEGER,
    distinct_commenters_status TEXT NOT NULL,

    reviewer_count          INTEGER,
    reviewer_count_status   TEXT NOT NULL,

    review_rounds           INTEGER,
    review_rounds_status    TEXT NOT NULL,

    files_changed           INTEGER,
    files_changed_status    TEXT NOT NULL,

    churn                   INTEGER,
    churn_status            TEXT NOT NULL,

    issue_link_present         INTEGER,
    issue_link_present_status  TEXT NOT NULL,

    issue_has_label            INTEGER,
    issue_has_label_status     TEXT NOT NULL,

    release_proximity          INTEGER,
    release_proximity_status   TEXT NOT NULL,

    reaction_count             INTEGER,
    reaction_count_status      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_p_features_repo ON event_p_features(repo_id);
"""

R_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_r_features (
    event_id              INTEGER PRIMARY KEY REFERENCES candidate_events(id) ON DELETE CASCADE,
    repo_id                INTEGER NOT NULL,

    maturity                 REAL,
    maturity_status          TEXT NOT NULL,

    files_survived           INTEGER,
    files_survived_status    TEXT NOT NULL,

    subsequent_modification_count         INTEGER,
    subsequent_modification_count_status  TEXT NOT NULL,

    releases_since_count           INTEGER,
    releases_since_count_status    TEXT NOT NULL,

    later_references_count         INTEGER,
    later_references_count_status  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_r_features_repo ON event_r_features(repo_id);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def reset_schema(conn: sqlite3.Connection) -> None:
    """Drop and recreate event_p_features, then re-run create_schema.

    Unlike Stage 2/3 tables, event_p_features has no external references
    (nothing joins *to* it) and extract_p_features() always fully
    regenerates every row for a repo on each run anyway — so during active
    feature-by-feature development, a plain CREATE TABLE IF NOT EXISTS
    would leave a stale schema behind every time a new feature column is
    added, since SQLite doesn't retroactively add columns. Called by
    scripts/extract_features.py specifically for that reason; create_schema
    alone stays available for callers that just need the table to exist
    without wiping it (e.g. a future read-only scoring script).
    """
    conn.execute("DROP TABLE IF EXISTS event_p_features")
    conn.commit()
    create_schema(conn)


def create_r_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(R_SCHEMA_SQL)
    conn.commit()


def reset_r_schema(conn: sqlite3.Connection) -> None:
    """Same reasoning as reset_schema, kept as a separate function (rather
    than folding into reset_schema) so re-running P extraction never wipes
    already-computed R data and vice versa — the two are extracted by
    separate scripts on separate schedules."""
    conn.execute("DROP TABLE IF EXISTS event_r_features")
    conn.commit()
    create_r_schema(conn)
