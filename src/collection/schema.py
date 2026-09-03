"""Raw evidence schema (Stage 1).

Tables here store repository evidence as collected, without identity
resolution, bot-filtering, or any other normalization — that happens in
Stage 2 (src/processing). Preserving raw evidence unmodified is a
reproducibility requirement (see CLAUDE.md Section 13/14).
"""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS repositories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    default_branch  TEXT,
    collected_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commits (
    repo_id              INTEGER NOT NULL REFERENCES repositories(id),
    hash                 TEXT NOT NULL,
    author_name          TEXT,
    author_email         TEXT,
    author_date          TEXT,
    committer_name       TEXT,
    committer_email      TEXT,
    committer_date       TEXT,
    message              TEXT,
    is_merge             INTEGER NOT NULL DEFAULT 0,
    parent_hashes        TEXT,
    insertions           INTEGER,
    deletions            INTEGER,
    files_changed_count  INTEGER,
    PRIMARY KEY (repo_id, hash)
);

CREATE TABLE IF NOT EXISTS commit_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id       INTEGER NOT NULL,
    commit_hash   TEXT NOT NULL,
    filename      TEXT,
    old_path      TEXT,
    change_type   TEXT,
    insertions    INTEGER,
    deletions     INTEGER,
    FOREIGN KEY (repo_id, commit_hash) REFERENCES commits(repo_id, hash)
);
CREATE INDEX IF NOT EXISTS idx_commit_files_commit
    ON commit_files(repo_id, commit_hash);

CREATE TABLE IF NOT EXISTS issues (
    id                  INTEGER PRIMARY KEY,
    repo_id             INTEGER NOT NULL REFERENCES repositories(id),
    number              INTEGER NOT NULL,
    title               TEXT,
    body                TEXT,
    state               TEXT,
    author_login        TEXT,
    created_at          TEXT,
    closed_at           TEXT,
    updated_at          TEXT,
    comments_truncated  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(repo_id, number)
);

CREATE TABLE IF NOT EXISTS issue_labels (
    issue_id  INTEGER NOT NULL REFERENCES issues(id),
    label     TEXT NOT NULL,
    PRIMARY KEY (issue_id, label)
);

CREATE TABLE IF NOT EXISTS issue_comments (
    id            INTEGER PRIMARY KEY,
    issue_id      INTEGER NOT NULL REFERENCES issues(id),
    author_login  TEXT,
    created_at    TEXT,
    body          TEXT
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id                INTEGER PRIMARY KEY,
    repo_id           INTEGER NOT NULL REFERENCES repositories(id),
    number            INTEGER NOT NULL,
    title             TEXT,
    body              TEXT,
    state             TEXT,
    author_login      TEXT,
    created_at        TEXT,
    merged_at         TEXT,
    closed_at         TEXT,
    updated_at        TEXT,
    base_branch       TEXT,
    head_branch       TEXT,
    merge_commit_sha  TEXT,
    reviews_truncated INTEGER NOT NULL DEFAULT 0,
    commits_truncated INTEGER NOT NULL DEFAULT 0,
    UNIQUE(repo_id, number)
);

CREATE TABLE IF NOT EXISTS pr_commits (
    pr_id        INTEGER NOT NULL REFERENCES pull_requests(id),
    commit_hash  TEXT NOT NULL,
    PRIMARY KEY (pr_id, commit_hash)
);

CREATE TABLE IF NOT EXISTS pr_labels (
    pr_id  INTEGER NOT NULL REFERENCES pull_requests(id),
    label  TEXT NOT NULL,
    PRIMARY KEY (pr_id, label)
);

CREATE TABLE IF NOT EXISTS pr_reviews (
    id              INTEGER PRIMARY KEY,
    pr_id           INTEGER NOT NULL REFERENCES pull_requests(id),
    reviewer_login  TEXT,
    state           TEXT,
    submitted_at    TEXT,
    body            TEXT
);

CREATE TABLE IF NOT EXISTS pr_review_comments (
    id            INTEGER PRIMARY KEY,
    pr_id         INTEGER NOT NULL REFERENCES pull_requests(id),
    review_id     INTEGER REFERENCES pr_reviews(id),
    author_login  TEXT,
    created_at    TEXT,
    body          TEXT,
    path          TEXT
);

CREATE TABLE IF NOT EXISTS releases (
    id             INTEGER PRIMARY KEY,
    repo_id        INTEGER NOT NULL REFERENCES repositories(id),
    tag_name       TEXT,
    name           TEXT,
    created_at     TEXT,
    published_at   TEXT,
    author_login   TEXT,
    body           TEXT,
    UNIQUE(repo_id, tag_name)
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all raw-evidence tables if they do not already exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enforced, schema ensured."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn
