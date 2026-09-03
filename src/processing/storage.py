"""Persistence for Stage 2 processed evidence.

Unlike Stage 1's raw storage (which accumulates incrementally across
re-runs against a live, changing repository), normalization is a full,
deterministic derivation from a fixed raw snapshot — so re-running it for
a repository clears and rewrites all of that repository's processed rows
rather than trying to patch them incrementally. That matches CLAUDE.md's
framing of data/processed/ as "derived from raw, regenerable."
"""

import datetime
import sqlite3

from src.processing.commits import RevertInfo
from src.processing.files import FileIdentityRecord
from src.processing.identity import ContributorRecord


def insert_contributors(conn: sqlite3.Connection, repo_id: int, contributors: list[ContributorRecord]) -> dict[int, int]:
    """Clears and rewrites all contributor data for this repo. Returns a
    mapping from the input list's index to the assigned database id, so
    callers can link commits/etc. to the right contributor row."""
    conn.execute("DELETE FROM contributor_git_identities WHERE repo_id = ?", (repo_id,))
    conn.execute("DELETE FROM contributor_github_identities WHERE repo_id = ?", (repo_id,))
    conn.execute("DELETE FROM contributors WHERE repo_id = ?", (repo_id,))

    index_to_db_id: dict[int, int] = {}
    for index, c in enumerate(contributors):
        cur = conn.execute(
            """
            INSERT INTO contributors (repo_id, canonical_name, canonical_email, github_login, is_bot, identity_confidence, merged_identity_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (repo_id, c.canonical_name, c.canonical_email, c.github_login, c.is_bot, c.identity_confidence, c.merged_identity_count),
        )
        db_id = cur.lastrowid
        index_to_db_id[index] = db_id

        conn.executemany(
            "INSERT INTO contributor_git_identities (repo_id, author_name, author_email, contributor_id) VALUES (?, ?, ?, ?)",
            [(repo_id, name, email, db_id) for name, email in c.git_identities],
        )
        conn.executemany(
            "INSERT INTO contributor_github_identities (repo_id, github_login, contributor_id) VALUES (?, ?, ?)",
            [(repo_id, login, db_id) for login in c.github_logins],
        )
    conn.commit()
    return index_to_db_id


def insert_commit_annotations(conn: sqlite3.Connection, repo_id: int, annotations: list[tuple[str, int | None, RevertInfo]]) -> None:
    """`annotations` is a list of (commit_hash, contributor_id_or_None, RevertInfo)."""
    conn.execute("DELETE FROM commit_annotations WHERE repo_id = ?", (repo_id,))
    conn.executemany(
        """
        INSERT INTO commit_annotations (repo_id, commit_hash, contributor_id, is_revert, reverts_commit_hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (repo_id, commit_hash, contributor_id, revert.is_revert, revert.reverts_commit_hash)
            for commit_hash, contributor_id, revert in annotations
        ],
    )
    conn.commit()


def insert_file_identities(conn: sqlite3.Connection, repo_id: int, files: list[FileIdentityRecord]) -> None:
    conn.execute("DELETE FROM file_path_history WHERE repo_id = ?", (repo_id,))
    conn.execute("DELETE FROM file_identities WHERE repo_id = ?", (repo_id,))

    for f in files:
        cur = conn.execute(
            "INSERT INTO file_identities (repo_id, first_path, last_path, is_deleted) VALUES (?, ?, ?, ?)",
            (repo_id, f.first_path, f.last_path, f.is_deleted),
        )
        file_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO file_path_history (repo_id, commit_hash, path, change_type, file_id) VALUES (?, ?, ?, ?, ?)",
            [(repo_id, obs.commit_hash, obs.path, obs.change_type, file_id) for obs in f.path_history],
        )
    conn.commit()


def insert_data_availability(
    conn: sqlite3.Connection, repo_id: int, *,
    has_releases: bool, has_pr_reviews: bool, has_issues: bool,
    earliest_commit_date: str | None, latest_commit_date: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO repository_data_availability
            (repo_id, has_releases, has_pr_reviews, has_issues, earliest_commit_date, latest_commit_date, normalized_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo_id) DO UPDATE SET
            has_releases=excluded.has_releases, has_pr_reviews=excluded.has_pr_reviews,
            has_issues=excluded.has_issues, earliest_commit_date=excluded.earliest_commit_date,
            latest_commit_date=excluded.latest_commit_date, normalized_at=excluded.normalized_at
        """,
        (repo_id, has_releases, has_pr_reviews, has_issues, earliest_commit_date, latest_commit_date,
         datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
