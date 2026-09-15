"""Persistence for Stage 3 candidate events.

Like Stage 2, event formation is a deterministic full derivation (from raw
+ processed evidence), so re-running it for a given (repo_id, granularity)
clears and rewrites those rows rather than patching incrementally.
"""

import sqlite3

from src.events.formation import CandidateEvent


def _resolve_contributor_id(
    processed_conn: sqlite3.Connection, repo_id: int,
    author_login: str | None, author_git_identity: tuple[str, str | None] | None,
) -> int | None:
    if author_login:
        row = processed_conn.execute(
            "SELECT contributor_id FROM contributor_github_identities WHERE repo_id = ? AND github_login = ?",
            (repo_id, author_login),
        ).fetchone()
        if row:
            return row[0]
    if author_git_identity:
        name, email = author_git_identity
        row = processed_conn.execute(
            "SELECT contributor_id FROM contributor_git_identities WHERE repo_id = ? AND author_name = ? AND author_email IS ?",
            (repo_id, name, email),
        ).fetchone()
        if row:
            return row[0]
    return None


def insert_events(
    processed_conn: sqlite3.Connection, repo_id: int, granularity: str, events: list[CandidateEvent],
) -> dict:
    # event_commits, and every later stage's per-event table
    # (event_p_features, event_r_features, event_p_scores, event_r_scores,
    # event_divergence), all declare event_id REFERENCES candidate_events(id)
    # ON DELETE CASCADE specifically so this delete alone is enough to
    # clear a repo's whole downstream analysis when its events are
    # regenerated — Stage 3 storage doesn't need to know those later
    # tables exist (CLAUDE.md Section 4: keep stages separate). Without
    # the cascade, re-running event formation against a repo that already
    # has P/R features/scores/divergence computed raised
    # sqlite3.IntegrityError, since those tables' rows still referenced
    # the about-to-be-deleted event ids.
    processed_conn.execute("DELETE FROM candidate_events WHERE repo_id = ? AND granularity = ?", (repo_id, granularity))

    unresolved_authors = 0
    for e in events:
        contributor_id = _resolve_contributor_id(processed_conn, repo_id, e.author_login, e.author_git_identity)
        if contributor_id is None:
            unresolved_authors += 1
        cur = processed_conn.execute(
            """
            INSERT INTO candidate_events
                (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, author_contributor_id, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (repo_id, granularity, e.event_type, e.source_pr_number, e.primary_commit_hash, e.title, contributor_id, e.occurred_at),
        )
        event_id = cur.lastrowid
        processed_conn.executemany(
            "INSERT INTO event_commits (event_id, commit_hash) VALUES (?, ?)",
            [(event_id, h) for h in e.commit_hashes],
        )
    processed_conn.commit()

    return {
        "granularity": granularity,
        "events_created": len(events),
        "unresolved_authors": unresolved_authors,
        "by_event_type": {
            event_type: sum(1 for e in events if e.event_type == event_type)
            for event_type in sorted({e.event_type for e in events})
        },
    }
