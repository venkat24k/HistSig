"""Processed-evidence schema (Stage 2).

Tables here are *derived* from data/raw/*.db — regenerable, never a source
of truth on their own (CLAUDE.md Section 14: raw is authoritative,
processed is derived). Nothing here is lossy: every resolution decision
(which raw identities were merged, which path a file was renamed from) is
recorded, not discarded, so provenance back to raw evidence is preserved
(CLAUDE.md Section 24).
"""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contributors (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id                 INTEGER NOT NULL,
    canonical_name          TEXT,
    canonical_email         TEXT,
    github_login            TEXT,
    is_bot                  INTEGER NOT NULL DEFAULT 0,
    identity_confidence     TEXT NOT NULL,
    merged_identity_count   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_contributors_repo ON contributors(repo_id);

-- Every distinct (author_name, author_email) pair seen in raw commits,
-- mapped to the contributor it was resolved to.
CREATE TABLE IF NOT EXISTS contributor_git_identities (
    repo_id         INTEGER NOT NULL,
    author_name     TEXT NOT NULL,
    author_email    TEXT NOT NULL,
    contributor_id  INTEGER NOT NULL REFERENCES contributors(id),
    PRIMARY KEY (repo_id, author_name, author_email)
);

-- Every distinct GitHub login seen anywhere in raw evidence (issues, PRs,
-- comments, reviews, releases), mapped to the contributor it belongs to.
CREATE TABLE IF NOT EXISTS contributor_github_identities (
    repo_id         INTEGER NOT NULL,
    github_login    TEXT NOT NULL,
    contributor_id  INTEGER NOT NULL REFERENCES contributors(id),
    PRIMARY KEY (repo_id, github_login)
);

-- Per-commit facts not present in raw evidence: resolved author, and
-- whether/what the commit reverts.
CREATE TABLE IF NOT EXISTS commit_annotations (
    repo_id               INTEGER NOT NULL,
    commit_hash           TEXT NOT NULL,
    contributor_id        INTEGER REFERENCES contributors(id),
    is_revert             INTEGER NOT NULL DEFAULT 0,
    reverts_commit_hash   TEXT,
    PRIMARY KEY (repo_id, commit_hash)
);

-- One row per canonical file identity, stable across renames.
CREATE TABLE IF NOT EXISTS file_identities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id     INTEGER NOT NULL,
    first_path  TEXT NOT NULL,
    last_path   TEXT NOT NULL,
    is_deleted  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_file_identities_repo ON file_identities(repo_id);

-- Every (commit, path) observation, linked to the canonical file identity
-- active at that point — this is what lets a later stage answer "does the
-- file this event touched still exist" even though its path changed.
--
-- file_id is part of the key, not just (repo_id, commit_hash, path):
-- a single commit can legitimately touch the same path twice under two
-- different identities (e.g. DELETE then ADD at the same path, which
-- build_file_identities treats as retiring the old file and starting a
-- new one — seen in real history, e.g. a submodule/symlink replaced by a
-- regular file at the same path in one commit).
CREATE TABLE IF NOT EXISTS file_path_history (
    repo_id      INTEGER NOT NULL,
    commit_hash  TEXT NOT NULL,
    path         TEXT NOT NULL,
    change_type  TEXT NOT NULL,
    file_id      INTEGER NOT NULL REFERENCES file_identities(id),
    PRIMARY KEY (repo_id, commit_hash, path, file_id)
);
CREATE INDEX IF NOT EXISTS idx_file_path_history_file ON file_path_history(file_id);

-- Explicit, repo-level record of what kinds of evidence this repository
-- actually has, so "zero reviews" (repo doesn't use PR review) and
-- "unavailable" are never conflated later (CLAUDE.md Section 20).
CREATE TABLE IF NOT EXISTS repository_data_availability (
    repo_id                 INTEGER PRIMARY KEY,
    has_releases            INTEGER NOT NULL,
    has_pr_reviews          INTEGER NOT NULL,
    has_issues               INTEGER NOT NULL,
    earliest_commit_date    TEXT,
    latest_commit_date      TEXT,
    normalized_at           TEXT NOT NULL
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn
