"""Perceived-significance (P) feature extraction — Phase 2, second half.

Each function here computes exactly one feature for exactly one event and
returns `(value, status)`. `status` is one of:

- "complete": value is a confident true count (0 is a valid complete value).
- "incomplete_lower_bound": value is real but known to be undercounted —
  some contributing raw table was truncated during collection (see the
  `*_truncated` flags on `pull_requests`, set in Stage 1).
- "not_applicable": the concept doesn't exist for this event (value is None).

The distinction matters: silently treating "not applicable" as 0, or an
undercounted value as a confident one, would make the least-discussed
events and the most-discussed-but-truncated events look identical to
downstream scoring — exactly backwards.

The first several features here only apply to `pull_request` events and
read from the raw `pull_requests` row plus one or more of its child
tables; `_get_pr_row` centralizes that lookup and its "not applicable"
cases so each feature function only has to say which child table(s) and
which truncation flag(s) it cares about — not every feature is incomplete
for the same reason (e.g. `reviewer_count` only cares whether *reviews*
were truncated, not whether individual review *comments* were).

`files_changed`/`churn` are the first features that apply to *every*
event type (a standalone commit has files and line changes even with no
PR at all), so they need `primary_commit_hash` too — added as an optional
trailing parameter on every function (defaulting to None) so the
PR-only features above didn't need to change.

`release_proximity` similarly applies to every event type but needs the
event's own timestamp rather than anything keyed by PR or commit hash, so
`occurred_at` was added the same way — one more optional trailing
parameter every function accepts (most ignore it).
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete_lower_bound"
STATUS_NOT_APPLICABLE = "not_applicable"


@dataclass
class _PRRow:
    id: int
    reviews_truncated: bool
    commits_truncated: bool
    review_comments_truncated: bool
    comments_truncated: bool
    closing_issues_truncated: bool
    reaction_count: int


def _get_pr_row(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None) -> _PRRow | None:
    if event_type != "pull_request" or source_pr_number is None:
        return None
    row = raw_conn.execute(
        """
        SELECT id, reviews_truncated, commits_truncated, review_comments_truncated, comments_truncated, closing_issues_truncated, reaction_count
        FROM pull_requests WHERE repo_id = ? AND number = ?
        """,
        (repo_id, source_pr_number),
    ).fetchone()
    if row is None:
        # A pr_bundle event references a PR that isn't in the raw table —
        # shouldn't happen for data produced by this pipeline, but a
        # foreign/edited processed DB could hit this; fail safe rather
        # than crash the whole extraction run.
        return None
    return _PRRow(id=row[0], reviews_truncated=bool(row[1]), commits_truncated=bool(row[2]),
                  review_comments_truncated=bool(row[3]), comments_truncated=bool(row[4]),
                  closing_issues_truncated=bool(row[5]), reaction_count=row[6])


def compute_comment_count(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[int | None, str]:
    """Total discussion volume: general PR conversation comments + inline
    code-review comments. Only defined for `pull_request` events —
    standalone commits and commit-level events have no comment channel at
    all in the current schema (commit messages aren't linked to issues),
    so they are `not_applicable`, not 0."""
    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    general = raw_conn.execute("SELECT COUNT(*) FROM pr_comments WHERE pr_id = ?", (pr.id,)).fetchone()[0]
    review_comments = raw_conn.execute("SELECT COUNT(*) FROM pr_review_comments WHERE pr_id = ?", (pr.id,)).fetchone()[0]
    total = general + review_comments

    # Any truncated contributing channel makes this a floor, not a true count.
    incomplete = pr.reviews_truncated or pr.review_comments_truncated or pr.comments_truncated
    return total, (STATUS_INCOMPLETE if incomplete else STATUS_COMPLETE)


def compute_distinct_commenters(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[int | None, str]:
    """Breadth of attention: how many distinct people commented (across
    both comment channels), not how many comments total — separates "one
    long back-and-forth between two people" from "many different people
    weighed in." Comments from deleted/"ghost" GitHub accounts
    (author_login is NULL) can't be attributed to a specific person, so
    they're excluded from the count rather than each treated as a distinct
    unknown commenter. Same event-type and truncation rules as
    `compute_comment_count` — they read the same underlying tables."""
    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    general_authors = {r[0] for r in raw_conn.execute("SELECT DISTINCT author_login FROM pr_comments WHERE pr_id = ?", (pr.id,))}
    review_authors = {r[0] for r in raw_conn.execute("SELECT DISTINCT author_login FROM pr_review_comments WHERE pr_id = ?", (pr.id,))}
    distinct = (general_authors | review_authors) - {None}

    incomplete = pr.reviews_truncated or pr.review_comments_truncated or pr.comments_truncated
    return len(distinct), (STATUS_INCOMPLETE if incomplete else STATUS_COMPLETE)


def compute_reviewer_count(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[int | None, str]:
    """Distinct people who submitted a *formal* review (approve/request-changes/
    comment via GitHub's review flow) — narrower and more structured than
    `distinct_commenters`, which also counts casual comments. A reviewer who
    approves silently (no body, no inline comments) shows up here but not in
    `distinct_commenters`, so this is deliberately not a subset of that
    feature — both are kept because they measure different things. Only
    depends on whether *reviews* were truncated; review-comment-level or
    general-comment truncation doesn't affect who's in the reviews list."""
    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    reviewers = {r[0] for r in raw_conn.execute("SELECT DISTINCT reviewer_login FROM pr_reviews WHERE pr_id = ?", (pr.id,))} - {None}

    return len(reviewers), (STATUS_INCOMPLETE if pr.reviews_truncated else STATUS_COMPLETE)


def compute_review_rounds(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[int | None, str]:
    """Total review *submissions* (every row in pr_reviews), not distinct
    reviewers — measures how much a change was iterated on, independent of
    how many people were involved. A single reviewer going back and forth
    with the author many times (request changes -> push -> re-review,
    repeated) produces a high review_rounds with a low reviewer_count;
    three people each reviewing once produces the opposite. Same
    truncation dependency as reviewer_count: only reviews_truncated."""
    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    total = raw_conn.execute("SELECT COUNT(*) FROM pr_reviews WHERE pr_id = ?", (pr.id,)).fetchone()[0]

    return total, (STATUS_INCOMPLETE if pr.reviews_truncated else STATUS_COMPLETE)


def _pr_commit_hashes_found_locally(raw_conn: sqlite3.Connection, repo_id: int, pr_id: int) -> tuple[list[str], bool]:
    """Returns (hashes that actually exist in our collected commits table,
    whether any linked commit is missing). A PR's commits can be missing
    from local history even when nothing was truncated during collection —
    squash-merge or rebase-merge rewrites the commits GitHub associates
    with the PR into new ones that never land on the default branch (see
    the pallets/click data validation report). That's a real, permanent
    gap in what can be measured, not a pagination cap, but it still means
    "the number computed from what we found" is a floor, not the true
    total — same `incomplete_lower_bound` semantics."""
    linked = [r[0] for r in raw_conn.execute("SELECT commit_hash FROM pr_commits WHERE pr_id = ?", (pr_id,))]
    if not linked:
        return [], False
    placeholders = ",".join("?" * len(linked))
    found = [r[0] for r in raw_conn.execute(f"SELECT hash FROM commits WHERE repo_id = ? AND hash IN ({placeholders})", [repo_id, *linked])]
    return found, len(found) < len(linked)


def compute_files_changed(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[int | None, str]:
    """Breadth of a change: distinct files touched. For a `pull_request`
    event, distinct across every commit GitHub associates with the PR that
    we can actually find in our collected history (see
    `_pr_commit_hashes_found_locally`). For `standalone_commit`/`commit`
    events, the single commit's own file count as PyDriller reported it —
    always a confident, complete value, since there's no pagination cap at
    the single-commit level."""
    if event_type in ("standalone_commit", "commit"):
        if primary_commit_hash is None:
            return None, STATUS_NOT_APPLICABLE
        row = raw_conn.execute(
            "SELECT files_changed_count FROM commits WHERE repo_id = ? AND hash = ?", (repo_id, primary_commit_hash)
        ).fetchone()
        return (None, STATUS_NOT_APPLICABLE) if row is None else (row[0], STATUS_COMPLETE)

    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    found, any_missing = _pr_commit_hashes_found_locally(raw_conn, repo_id, pr.id)
    if not found:
        distinct_files = 0
    else:
        placeholders = ",".join("?" * len(found))
        distinct_files = raw_conn.execute(
            f"SELECT COUNT(DISTINCT filename) FROM commit_files WHERE repo_id = ? AND commit_hash IN ({placeholders})",
            [repo_id, *found],
        ).fetchone()[0]

    incomplete = any_missing or pr.commits_truncated
    return distinct_files, (STATUS_INCOMPLETE if incomplete else STATUS_COMPLETE)


def compute_churn(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[int | None, str]:
    """Volume of a change: total lines touched (insertions + deletions).
    Same event-type handling and completeness rules as `files_changed` —
    they read the same commit set, just summed differently."""
    if event_type in ("standalone_commit", "commit"):
        if primary_commit_hash is None:
            return None, STATUS_NOT_APPLICABLE
        row = raw_conn.execute(
            "SELECT insertions, deletions FROM commits WHERE repo_id = ? AND hash = ?", (repo_id, primary_commit_hash)
        ).fetchone()
        return (None, STATUS_NOT_APPLICABLE) if row is None else ((row[0] or 0) + (row[1] or 0), STATUS_COMPLETE)

    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    found, any_missing = _pr_commit_hashes_found_locally(raw_conn, repo_id, pr.id)
    if not found:
        total = 0
    else:
        placeholders = ",".join("?" * len(found))
        row = raw_conn.execute(
            f"SELECT COALESCE(SUM(insertions),0), COALESCE(SUM(deletions),0) FROM commits WHERE repo_id = ? AND hash IN ({placeholders})",
            [repo_id, *found],
        ).fetchone()
        total = row[0] + row[1]

    incomplete = any_missing or pr.commits_truncated
    return total, (STATUS_INCOMPLETE if incomplete else STATUS_COMPLETE)


def compute_issue_link_present(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[bool | None, str]:
    """Whether this PR was linked to an issue GitHub itself resolved as
    "closed by" this PR (`pr_closing_issues`, sourced from GitHub's
    `closingIssuesReferences` — the same signal GitHub uses to auto-close
    an issue on merge). This is deliberately not a text search for
    "fixes #123" in the PR body: GitHub's own resolution is authoritative
    (it validates the issue exists, handles alternate keywords, and is
    kept in sync as the PR is edited), where a regex would be a guess.

    Only defined for `pull_request` events — `closingIssuesReferences` is
    a PR-level GraphQL field with no equivalent for a raw commit, so
    standalone commits and commit-level events are `not_applicable`
    rather than assumed False.

    Truncation can only make this *lose* a true positive, never manufacture
    a false one: pagination returns up to a fixed page size, so if the
    total exceeds what we fetched, at least one row was already returned
    and `present` is already True. It can only affect a PR where we found
    zero rows and still don't know whether more exist — hence checked
    only in that branch."""
    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    count = raw_conn.execute("SELECT COUNT(*) FROM pr_closing_issues WHERE pr_id = ?", (pr.id,)).fetchone()[0]
    present = count > 0

    incomplete = pr.closing_issues_truncated and not present
    return present, (STATUS_INCOMPLETE if incomplete else STATUS_COMPLETE)


def compute_issue_has_label(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[bool | None, str]:
    """Whether any issue this PR closes (via `pr_closing_issues`, see
    `compute_issue_link_present`) carries at least one label.

    Deliberately not a severity/priority classifier. Before building this
    feature, the real label vocabulary in both test repositories was
    checked: pallets/click's issue and PR labels are entirely topical
    ('parsing', 'docs', 'shell completion', ...) with nothing indicating
    severity or priority, and pallets/markupsafe has zero issue labels at
    all (one PR, out of hundreds, is ever labeled 'security'). A
    keyword-matched severity vocabulary ('bug', 'critical', 'P0', ...)
    would be an invented category with almost no real support in either
    repository. "Was the linked issue triaged/labeled at all" is a
    weaker but honest signal built only from data already collected —
    see the discussion recorded when this feature was defined.

    Only defined when the PR has at least one linked issue (same
    not_applicable boundary as `compute_issue_link_present` — no link
    means there's no issue to check labels on at all). A linked issue
    number that isn't in our own `issues` table (e.g. a cross-repository
    reference, or one Stage 1 didn't collect) can't have its labels
    checked either way; if that leaves nothing to check, or if the PR's
    closing-issue list was itself truncated, and no label was found, the
    value is a floor rather than a confident False — a label could exist
    on evidence we don't have."""
    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    linked_numbers = [r[0] for r in raw_conn.execute(
        "SELECT issue_number FROM pr_closing_issues WHERE pr_id = ?", (pr.id,)
    )]
    if not linked_numbers:
        return None, STATUS_NOT_APPLICABLE

    placeholders = ",".join("?" * len(linked_numbers))
    issue_ids = [r[0] for r in raw_conn.execute(
        f"SELECT id FROM issues WHERE repo_id = ? AND number IN ({placeholders})",
        [repo_id, *linked_numbers],
    )]
    any_unresolved = len(issue_ids) < len(linked_numbers)

    if not issue_ids:
        has_label = False
    else:
        placeholders2 = ",".join("?" * len(issue_ids))
        count = raw_conn.execute(
            f"SELECT COUNT(*) FROM issue_labels WHERE issue_id IN ({placeholders2})", issue_ids
        ).fetchone()[0]
        has_label = count > 0

    incomplete = (pr.closing_issues_truncated or any_unresolved) and not has_label
    return has_label, (STATUS_INCOMPLETE if incomplete else STATUS_COMPLETE)


def compute_release_proximity(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[int | None, str]:
    """Seconds between this event and the next release published after it
    — how soon the change shipped, not how long the project had already
    been between releases. Applies to every event type equally: releases
    are a repo-wide timeline, not something tied to having a PR or a
    specific commit.

    `not_applicable` when no release was ever published after this
    event — either the repository has no releases at all, or the event
    is more recent than every release Stage 1 collected. This is not "the
    concept doesn't apply" in the usual sense (a next release could
    always in principle exist); it means the necessary future evidence
    isn't in our collected data yet, which is the closest fit the
    three-value status taxonomy offers, and it is rare in practice (~1%
    of events in pallets/click, verified before writing this function).

    Timestamps (`candidate_events.occurred_at`, `releases.published_at`)
    are both Stage-1 GraphQL ISO-8601 strings with a 'Z' UTC suffix, so
    plain string comparison in SQL already orders them correctly — no
    extra normalization needed to find the nearest subsequent release."""
    if occurred_at is None:
        return None, STATUS_NOT_APPLICABLE

    next_release_at = raw_conn.execute(
        "SELECT MIN(published_at) FROM releases WHERE repo_id = ? AND published_at > ?",
        (repo_id, occurred_at),
    ).fetchone()[0]
    if next_release_at is None:
        return None, STATUS_NOT_APPLICABLE

    delta_seconds = int(
        (datetime.fromisoformat(next_release_at) - datetime.fromisoformat(occurred_at)).total_seconds()
    )
    return delta_seconds, STATUS_COMPLETE


def compute_reaction_count(raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, primary_commit_hash: str | None = None, occurred_at: str | None = None) -> tuple[int | None, str]:
    """GitHub emoji-reaction total on the PR itself (`reactions.totalCount`)
    — a lighter-weight attention signal than `comment_count`: someone can
    react without ever writing anything, so this captures passive
    engagement comment-based features miss entirely.

    Checked against real data before building this: a sample of the most
    recent 20 PRs in each test repo had reactions on roughly 5-25% of
    items — sparse, but real and present in both repos (unlike the label
    vocabulary check that led to redefining `issue_has_label`, where
    markupsafe had essentially none).

    Only defined for `pull_request` events — reactions in this schema are
    only collected on the PR node itself, not on standalone commits (which
    have no PR to react to) or on individual comments (not collected,
    kept out of scope for this first pass).

    Always `complete` when applicable: `reactions.totalCount` is a single
    aggregate GitHub computes and returns directly, not a paginated
    connection we page through ourselves, so there is no truncation
    scenario the way there is for comments or reviews."""
    pr = _get_pr_row(raw_conn, repo_id, event_type, source_pr_number)
    if pr is None:
        return None, STATUS_NOT_APPLICABLE

    return pr.reaction_count, STATUS_COMPLETE
