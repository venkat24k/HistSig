"""Idempotent persistence of collected evidence into the raw SQLite schema.

Re-running collection against the same repository must not create
duplicate rows — each insert function here is safe to call repeatedly with
overlapping data (see CLAUDE.md Section 26: the collector must be
re-runnable).
"""

import datetime
import sqlite3

from src.collection.git_collector import CommitRecord
from src.collection.github_collector import IssueRecord, PullRequestRecord, ReleaseRecord


def upsert_repository(conn: sqlite3.Connection, url: str, name: str, default_branch: str | None = None) -> int:
    """Insert a repository row if it doesn't exist yet; return its id.

    `collected_at` is only set on first insert — re-running collection for
    an already-known repository does not overwrite the original collection
    timestamp here (per-run collection metadata belongs in a future
    collection-run log, not in this table).
    """
    cur = conn.execute("SELECT id FROM repositories WHERE url = ?", (url,))
    row = cur.fetchone()
    if row is not None:
        return row[0]

    cur = conn.execute(
        """
        INSERT INTO repositories (url, name, default_branch, collected_at)
        VALUES (?, ?, ?, ?)
        """,
        (url, name, default_branch, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def _replace_children(conn: sqlite3.Connection, delete_sql: str, delete_params: tuple, insert_sql: str, rows: list[tuple]) -> None:
    """Child tables (commit_files, issue_comments, pr_reviews, ...) have a
    surrogate id rather than a natural key, so idempotency is handled by
    clearing a parent's existing child rows before re-inserting — shared
    here since every entity with child tables repeated this same two-step
    pattern independently."""
    conn.execute(delete_sql, delete_params)
    if rows:
        conn.executemany(insert_sql, rows)


def insert_commits(conn: sqlite3.Connection, repo_id: int, commits: list[CommitRecord]) -> None:
    for commit in commits:
        conn.execute(
            """
            INSERT INTO commits (
                repo_id, hash, author_name, author_email, author_date,
                committer_name, committer_email, committer_date, message,
                is_merge, parent_hashes, insertions, deletions, files_changed_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_id, hash) DO UPDATE SET
                author_name=excluded.author_name,
                author_email=excluded.author_email,
                author_date=excluded.author_date,
                committer_name=excluded.committer_name,
                committer_email=excluded.committer_email,
                committer_date=excluded.committer_date,
                message=excluded.message,
                is_merge=excluded.is_merge,
                parent_hashes=excluded.parent_hashes,
                insertions=excluded.insertions,
                deletions=excluded.deletions,
                files_changed_count=excluded.files_changed_count
            """,
            (
                repo_id,
                commit.hash,
                commit.author_name,
                commit.author_email,
                commit.author_date,
                commit.committer_name,
                commit.committer_email,
                commit.committer_date,
                commit.message,
                commit.is_merge,
                ",".join(commit.parent_hashes),
                commit.insertions,
                commit.deletions,
                commit.files_changed_count,
            ),
        )

        _replace_children(
            conn,
            "DELETE FROM commit_files WHERE repo_id = ? AND commit_hash = ?", (repo_id, commit.hash),
            """
            INSERT INTO commit_files (repo_id, commit_hash, filename, old_path, change_type, insertions, deletions)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [(repo_id, commit.hash, f.filename, f.old_path, f.change_type, f.insertions, f.deletions) for f in commit.files],
        )
    conn.commit()


def insert_issues(conn: sqlite3.Connection, repo_id: int, issues: list[IssueRecord]) -> None:
    for issue in issues:
        conn.execute(
            """
            INSERT INTO issues (id, repo_id, number, title, body, state, author_login, created_at, closed_at, updated_at, comments_truncated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, body=excluded.body, state=excluded.state,
                author_login=excluded.author_login, created_at=excluded.created_at,
                closed_at=excluded.closed_at, updated_at=excluded.updated_at,
                comments_truncated=excluded.comments_truncated
            """,
            (issue.id, repo_id, issue.number, issue.title, issue.body, issue.state,
             issue.author_login, issue.created_at, issue.closed_at, issue.updated_at,
             issue.comments_truncated),
        )

        _replace_children(
            conn,
            "DELETE FROM issue_labels WHERE issue_id = ?", (issue.id,),
            "INSERT INTO issue_labels (issue_id, label) VALUES (?, ?)",
            [(issue.id, label) for label in issue.labels],
        )
        _replace_children(
            conn,
            "DELETE FROM issue_comments WHERE issue_id = ?", (issue.id,),
            "INSERT INTO issue_comments (id, issue_id, author_login, created_at, body) VALUES (?, ?, ?, ?, ?)",
            [(c.id, issue.id, c.author_login, c.created_at, c.body) for c in issue.comments],
        )
    conn.commit()


def insert_pull_requests(conn: sqlite3.Connection, repo_id: int, pull_requests: list[PullRequestRecord]) -> None:
    for pr in pull_requests:
        conn.execute(
            """
            INSERT INTO pull_requests (
                id, repo_id, number, title, body, state, author_login, created_at,
                merged_at, closed_at, updated_at, base_branch, head_branch, merge_commit_sha,
                reviews_truncated, commits_truncated, review_comments_truncated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, body=excluded.body, state=excluded.state,
                author_login=excluded.author_login, created_at=excluded.created_at,
                merged_at=excluded.merged_at, closed_at=excluded.closed_at, updated_at=excluded.updated_at,
                base_branch=excluded.base_branch, head_branch=excluded.head_branch,
                merge_commit_sha=excluded.merge_commit_sha,
                reviews_truncated=excluded.reviews_truncated, commits_truncated=excluded.commits_truncated,
                review_comments_truncated=excluded.review_comments_truncated
            """,
            (pr.id, repo_id, pr.number, pr.title, pr.body, pr.state, pr.author_login, pr.created_at,
             pr.merged_at, pr.closed_at, pr.updated_at, pr.base_branch, pr.head_branch, pr.merge_commit_sha,
             pr.reviews_truncated, pr.commits_truncated, pr.review_comments_truncated),
        )

        _replace_children(
            conn,
            "DELETE FROM pr_labels WHERE pr_id = ?", (pr.id,),
            "INSERT INTO pr_labels (pr_id, label) VALUES (?, ?)",
            [(pr.id, label) for label in pr.labels],
        )
        _replace_children(
            conn,
            "DELETE FROM pr_commits WHERE pr_id = ?", (pr.id,),
            "INSERT INTO pr_commits (pr_id, commit_hash) VALUES (?, ?)",
            [(pr.id, sha) for sha in pr.commit_shas],
        )
        # pr_review_comments references pr_reviews via review_id, so child
        # rows are cleared before the reviews they point to.
        conn.execute("DELETE FROM pr_review_comments WHERE pr_id = ?", (pr.id,))
        _replace_children(
            conn,
            "DELETE FROM pr_reviews WHERE pr_id = ?", (pr.id,),
            "INSERT INTO pr_reviews (id, pr_id, reviewer_login, state, submitted_at, body) VALUES (?, ?, ?, ?, ?, ?)",
            [(r.id, pr.id, r.reviewer_login, r.state, r.submitted_at, r.body) for r in pr.reviews],
        )
        if pr.review_comments:
            conn.executemany(
                """
                INSERT INTO pr_review_comments (id, pr_id, review_id, author_login, created_at, body, path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(rc.id, pr.id, rc.review_id, rc.author_login, rc.created_at, rc.body, rc.path) for rc in pr.review_comments],
            )
    conn.commit()


def insert_releases(conn: sqlite3.Connection, repo_id: int, releases: list[ReleaseRecord]) -> None:
    for rel in releases:
        conn.execute(
            """
            INSERT INTO releases (id, repo_id, tag_name, name, created_at, published_at, author_login, body)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tag_name=excluded.tag_name, name=excluded.name, created_at=excluded.created_at,
                published_at=excluded.published_at, author_login=excluded.author_login, body=excluded.body
            """,
            (rel.id, repo_id, rel.tag_name, rel.name, rel.created_at, rel.published_at, rel.author_login, rel.body),
        )
    conn.commit()
