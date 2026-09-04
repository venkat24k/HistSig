"""Candidate historical event schema (Stage 3).

Lives in the same processed-data SQLite file as Stage 2's tables (still
derived/regenerable data, just a further transformation — see CLAUDE.md
Section 14). `granularity` makes the event-grouping rule an explicit,
switchable setting rather than a single hard-coded choice, so more than
one definition can be generated and compared side by side without losing
anything: the underlying commits and PRs are never altered, only grouped
differently.
"""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candidate_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id                 INTEGER NOT NULL,
    granularity             TEXT NOT NULL,
    event_type              TEXT NOT NULL,
    source_pr_number        INTEGER,
    primary_commit_hash     TEXT,
    title                   TEXT,
    author_contributor_id   INTEGER,
    occurred_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candidate_events_repo_granularity
    ON candidate_events(repo_id, granularity);

-- Every commit belonging to an event, in whatever quantity that event's
-- granularity implies (1 for a standalone-commit/commit-level event, 1+
-- for a pr_bundle event). Commit hashes here are exactly what the raw
-- pr_commits table recorded — some may not exist in the local commits
-- table (squash/rebase-merged PRs whose original commits never landed on
-- the default branch; see the pallets/click validation report) and that
-- is expected, not an error, at this stage.
CREATE TABLE IF NOT EXISTS event_commits (
    event_id     INTEGER NOT NULL REFERENCES candidate_events(id),
    commit_hash  TEXT NOT NULL,
    PRIMARY KEY (event_id, commit_hash)
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
