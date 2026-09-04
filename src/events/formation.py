"""Candidate historical event formation (Stage 3).

Two supported granularities — kept as an explicit parameter rather than a
single hard-coded rule, so both can be generated and compared later
without re-deriving anything (nothing about the underlying commits/PRs
changes, only how they're grouped):

- "pr_bundle": a merged/closed/open pull request is one event, bundling
  all of its commits; a commit that never belonged to any pull request
  (a direct push, common in smaller or pre-PR-workflow repositories) is
  its own event. This is the primary/default definition.
- "commit_level": every commit is its own event, no bundling at all.

Every pull request becomes an event regardless of its state (open, closed
unmerged, or merged) — an abandoned or rejected PR is still a real
historical event (discussion happened, even if nothing landed), and
excluding it would bias the dataset toward only "successful" changes.
"""

import sqlite3
from dataclasses import dataclass, field


@dataclass
class CandidateEvent:
    granularity: str
    event_type: str  # "pull_request" | "standalone_commit" | "commit"
    source_pr_number: int | None
    primary_commit_hash: str | None
    title: str
    author_login: str | None
    # (name, email) with email normalized to None when empty — must match
    # identity.py's `email or None` normalization exactly, since storage.py
    # looks this up against Stage 2's contributor_git_identities table,
    # which was built with that same normalization.
    author_git_identity: tuple[str, str | None] | None
    occurred_at: str
    commit_hashes: list[str] = field(default_factory=list)


def _first_line(message: str | None) -> str:
    message = (message or "").strip()
    return message.splitlines()[0] if message else "(no message)"


def form_pr_bundle_events(raw_conn: sqlite3.Connection) -> list[CandidateEvent]:
    events = []
    for pr_id, number, title, author_login, created_at, merged_at, closed_at in raw_conn.execute(
        "SELECT id, number, title, author_login, created_at, merged_at, closed_at FROM pull_requests"
    ):
        commit_hashes = [row[0] for row in raw_conn.execute("SELECT commit_hash FROM pr_commits WHERE pr_id = ?", (pr_id,))]
        # Occurred-at prefers merged_at (the moment it actually took effect),
        # falling back to closed_at (rejected/abandoned PRs never merge),
        # falling back to created_at (still-open PRs have neither).
        occurred_at = merged_at or closed_at or created_at
        events.append(
            CandidateEvent(
                granularity="pr_bundle", event_type="pull_request",
                source_pr_number=number, primary_commit_hash=None,
                title=title or "(no title)", author_login=author_login, author_git_identity=None,
                occurred_at=occurred_at, commit_hashes=commit_hashes,
            )
        )
    return events


def form_standalone_commit_events(raw_conn: sqlite3.Connection) -> list[CandidateEvent]:
    events = []
    for hash_, message, author_name, author_email, author_date_utc in raw_conn.execute(
        """
        SELECT hash, message, author_name, author_email, author_date_utc
        FROM commits
        WHERE hash NOT IN (SELECT commit_hash FROM pr_commits)
        """
    ):
        events.append(
            CandidateEvent(
                granularity="pr_bundle", event_type="standalone_commit",
                source_pr_number=None, primary_commit_hash=hash_,
                title=_first_line(message), author_login=None, author_git_identity=(author_name, author_email or None),
                occurred_at=author_date_utc, commit_hashes=[hash_],
            )
        )
    return events


def form_commit_level_events(raw_conn: sqlite3.Connection) -> list[CandidateEvent]:
    events = []
    for hash_, message, author_name, author_email, author_date_utc in raw_conn.execute(
        "SELECT hash, message, author_name, author_email, author_date_utc FROM commits"
    ):
        events.append(
            CandidateEvent(
                granularity="commit_level", event_type="commit",
                source_pr_number=None, primary_commit_hash=hash_,
                title=_first_line(message), author_login=None, author_git_identity=(author_name, author_email or None),
                occurred_at=author_date_utc, commit_hashes=[hash_],
            )
        )
    return events


def form_events(raw_conn: sqlite3.Connection, granularity: str) -> list[CandidateEvent]:
    if granularity == "pr_bundle":
        return form_pr_bundle_events(raw_conn) + form_standalone_commit_events(raw_conn)
    if granularity == "commit_level":
        return form_commit_level_events(raw_conn)
    raise ValueError(f"Unknown event granularity: {granularity!r}. Expected 'pr_bundle' or 'commit_level'.")
