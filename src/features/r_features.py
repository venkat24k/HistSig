"""Historical-salience (R) feature extraction — Phase 2, third quarter.

Same status taxonomy as p_features.py: `complete` / `incomplete_lower_bound`
/ `not_applicable`, for the same reason (CLAUDE.md Section 20) — never let
"the concept doesn't apply" or "undercounted" collapse into a plain 0.

Per CLAUDE.md Section 34's settled R design: R is computed for every
event regardless of age — no hard cutoff that would discard a young
repository's entire recent history. Instead, every event separately
carries a `maturity` value: the fraction of the repository's *entire*
observed history that happened after this event. `maturity` is not a P/R
feature with a weight of its own; it's context every other R feature
needs when its value gets used downstream. An event with `maturity` near
0 happened right at the edge of collected history — nothing has had time
to happen to it yet, so a low `files_survived` count there means "too
early to judge," not "this didn't matter." An event with `maturity` near
1 sits near the start of history — almost everything collected happened
after it, so R had its full chance to show up.

Most features here read only `processed_conn` — Stage 2's
`file_identities`/`file_path_history` (built specifically to support file
survival; see src/processing/files.py), `repository_data_availability`,
and Stage 3's `commit_level` candidate events already carry everything
those need, no raw evidence required. `releases_since_count` is the
exception: releases are collected in Stage 1 and never copied into the
processed database, so it takes `raw_conn` the same way p_features.py's
`compute_release_proximity` does.
"""

import sqlite3
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime

STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete_lower_bound"
STATUS_NOT_APPLICABLE = "not_applicable"


def compute_maturity(earliest_commit_date: str | None, latest_commit_date: str | None, occurred_at: str) -> tuple[float | None, str]:
    """(latest_commit_date - occurred_at) / (latest_commit_date - earliest_commit_date).

    `not_applicable` when the repository's observation window can't be
    read (Stage 2 hasn't run) or has zero span (a repository with only a
    single collected commit date) — the ratio is undefined, not zero, in
    that case.

    Also `not_applicable` when `occurred_at` falls outside
    [earliest_commit_date, latest_commit_date] — verified against real
    data before treating this as done: 12 of pallets/markupsafe's
    `pull_request` events came out with a negative maturity. Every one was
    a PR whose `occurred_at` (created/closed date, since it never merged
    any commits — see formation.py's fallback chain) fell *after*
    `latest_commit_date`, because a still-open or commit-less-closed PR
    can have activity beyond the observed commit window — `occurred_at`
    isn't bounded by "the latest commit we collected" the way a commit's
    own date always is. Rather than a nonsensical out-of-[0,1] ratio,
    that's correctly "we don't have a valid observation window to judge
    this event's maturity against yet," not a computable value."""
    if earliest_commit_date is None or latest_commit_date is None:
        return None, STATUS_NOT_APPLICABLE

    earliest = datetime.fromisoformat(earliest_commit_date)
    latest = datetime.fromisoformat(latest_commit_date)
    occurred = datetime.fromisoformat(occurred_at)
    window = (latest - earliest).total_seconds()
    if window <= 0:
        return None, STATUS_NOT_APPLICABLE
    if occurred < earliest or occurred > latest:
        return None, STATUS_NOT_APPLICABLE

    return (latest - occurred).total_seconds() / window, STATUS_COMPLETE


def _event_commit_hashes(processed_conn: sqlite3.Connection, event_id: int) -> list[str]:
    return [r[0] for r in processed_conn.execute("SELECT commit_hash FROM event_commits WHERE event_id = ?", (event_id,))]


def _resolve_event_file_ids(processed_conn: sqlite3.Connection, repo_id: int, commit_hashes: list[str]) -> tuple[set[int], bool]:
    """Given an event's own commit hashes, returns (distinct file_ids they
    touched, any_missing) — shared by every R feature that needs "which
    files did this event touch."

    Completeness is checked against `commit_annotations` (populated for
    *every* raw commit, regardless of whether it touched any files — see
    normalize.py), not against `file_path_history` directly. That
    distinction matters: about 37% of pallets/markupsafe's commits are
    merge commits with zero recorded file changes (PyDriller doesn't diff
    merges by default), and a merge commit that genuinely touched no files
    is a real, complete zero — not a gap. Checking `file_path_history`
    directly for "is this commit missing" would have wrongly flagged every
    one of those as incomplete (verified against real data before writing
    this the second time: markupsafe's incomplete rate came out at 43% on
    the first attempt, which didn't match any real evidence gap of that
    size — cross-checked with `commit_files`/`is_merge` and traced to
    exactly this). Only a commit_hash genuinely absent from
    `commit_annotations` (never collected at all — the same squash-merge
    gap as P's `files_changed`) counts as missing evidence."""
    if not commit_hashes:
        return set(), False

    placeholders = ",".join("?" * len(commit_hashes))
    known_hashes = {
        r[0] for r in processed_conn.execute(
            f"SELECT commit_hash FROM commit_annotations WHERE repo_id = ? AND commit_hash IN ({placeholders})",
            [repo_id, *commit_hashes],
        )
    }
    any_missing = len(known_hashes) < len(commit_hashes)

    file_ids = {
        r[0] for r in processed_conn.execute(
            f"SELECT DISTINCT file_id FROM file_path_history WHERE repo_id = ? AND commit_hash IN ({placeholders})",
            [repo_id, *commit_hashes],
        )
    }
    return file_ids, any_missing


def compute_files_survived(processed_conn: sqlite3.Connection, repo_id: int, event_id: int) -> tuple[int | None, str]:
    """How many of the distinct files this event touched are still present
    (not deleted) as of the latest collected state — `file_identities`
    tracks this across renames, so a file that moved is still counted as
    the same file surviving, not as one file dying and a new one appearing.

    A count, not a fraction: unlike a ratio, a count found from a partial
    commit set is still a real, confirmed lower bound (every file counted
    here really is alive; discovering more of the event's commits could
    only ever add more confirmed-alive files, never invalidate one already
    counted) — the same `incomplete_lower_bound` semantics as
    `compute_files_changed` in p_features.py, and for the identical reason
    (a PR's linked commits aren't always all found locally; see
    `_pr_commit_hashes_found_locally`'s docstring there).

    `not_applicable` only when the event has no linked commits at all (a
    PR whose commit list Stage 1 collected as empty)."""
    commit_hashes = _event_commit_hashes(processed_conn, event_id)
    if not commit_hashes:
        return None, STATUS_NOT_APPLICABLE

    file_ids, any_missing = _resolve_event_file_ids(processed_conn, repo_id, commit_hashes)

    if not file_ids:
        survived = 0
    else:
        placeholders = ",".join("?" * len(file_ids))
        survived = processed_conn.execute(
            f"SELECT COUNT(*) FROM file_identities WHERE id IN ({placeholders}) AND is_deleted = 0",
            list(file_ids),
        ).fetchone()[0]

    return survived, (STATUS_INCOMPLETE if any_missing else STATUS_COMPLETE)


FileTouchIndex = dict[int, list[tuple[str, str]]]


def build_file_touch_index(processed_conn: sqlite3.Connection, repo_id: int) -> FileTouchIndex:
    """One query for the *whole repository*: {file_id: [(occurred_at,
    commit_hash), ...]} sorted by occurred_at, for every file touched by
    any commit with a known commit_level date.

    Exists purely as a performance fast path for `extract_r_features`,
    which calls this once and passes the result to every event's
    `compute_subsequent_modification_count` call. Without it, that
    function's per-event query re-scans a file's entire touch history
    from scratch every time *any* event touches that file — for a
    frequently-touched file (a core module edited by hundreds of commits,
    itself touched by hundreds of different events across a repository's
    history), that redundant re-scanning is what made a first attempt at
    this stall on pallets/click (6,768 events) for minutes with no
    result. Precomputing each file's sorted touch list once and reusing
    it via binary search (`bisect_right`) turns that into a single linear
    pass plus O(events x files_per_event x log(touches_per_file))
    lookups — the same information, computed once instead of once per
    event that happens to share a file."""
    rows = processed_conn.execute(
        """
        SELECT fph.file_id, ce.occurred_at, fph.commit_hash
        FROM file_path_history fph
        JOIN candidate_events ce
            ON ce.primary_commit_hash = fph.commit_hash AND ce.granularity = 'commit_level' AND ce.repo_id = fph.repo_id
        WHERE fph.repo_id = ?
        """,
        (repo_id,),
    ).fetchall()

    index: FileTouchIndex = defaultdict(list)
    for file_id, occurred_at, commit_hash in rows:
        index[file_id].append((occurred_at, commit_hash))
    for touches in index.values():
        touches.sort(key=lambda t: t[0])
    return dict(index)


def compute_subsequent_modification_count(
    processed_conn: sqlite3.Connection,
    repo_id: int,
    event_id: int,
    occurred_at: str,
    file_touch_index: FileTouchIndex | None = None,
) -> tuple[int | None, str]:
    """How many *distinct later commits* touched any of the files this
    event touched — repeated maintenance / an actively-worked-on file,
    one of CLAUDE.md Section 2's named R candidates. Counts distinct
    commits, not total touches, so a single later commit that happens to
    modify three of the event's files counts once, not three times.

    "Later" is checked via each candidate commit's own `commit_level`
    candidate event (`occurred_at` = `author_date_utc`) compared against
    this event's own `occurred_at` — reuses data already computed in
    Stage 3 rather than needing a raw commit-date lookup, so this stays
    processed-database-only like `files_survived`. The event's own commit
    hashes are excluded explicitly (not just by the date filter): a
    multi-commit `pull_request` event's `occurred_at` is the PR's
    merged/closed/created date, not any individual commit's date, so nothing
    guarantees a commit strictly precedes its own PR's timestamp.

    Same lower-bound reasoning as `files_survived`: a count from a
    partially-resolved file set is still a real lower bound (discovering
    more of the event's own files could only add more, never remove,
    later modifications already found), so this reuses
    `_resolve_event_file_ids`'s `any_missing` for its own
    `incomplete_lower_bound` status. `not_applicable` only when the event
    has no linked commits at all.

    `file_touch_index` (from `build_file_touch_index`) is an optional
    fast path: when given, "later touches" are found via in-memory binary
    search instead of a fresh SQL query — see that function's docstring
    for why the default (query-per-call) path doesn't scale to a
    whole-repository extraction run. Both paths compute the identical
    result; the index is purely a performance choice, verified to agree
    with the query path in tests."""
    commit_hashes = _event_commit_hashes(processed_conn, event_id)
    if not commit_hashes:
        return None, STATUS_NOT_APPLICABLE

    file_ids, any_missing = _resolve_event_file_ids(processed_conn, repo_id, commit_hashes)

    if not file_ids:
        count = 0
    elif file_touch_index is not None:
        own = set(commit_hashes)
        later_commits: set[str] = set()
        for file_id in file_ids:
            touches = file_touch_index.get(file_id, [])
            start = bisect_right(touches, occurred_at, key=lambda t: t[0])
            for _, commit_hash in touches[start:]:
                if commit_hash not in own:
                    later_commits.add(commit_hash)
        count = len(later_commits)
    else:
        file_placeholders = ",".join("?" * len(file_ids))
        commit_placeholders = ",".join("?" * len(commit_hashes))
        rows = processed_conn.execute(
            f"""
            SELECT DISTINCT fph.commit_hash
            FROM file_path_history fph
            JOIN candidate_events ce
                ON ce.primary_commit_hash = fph.commit_hash AND ce.granularity = 'commit_level' AND ce.repo_id = fph.repo_id
            WHERE fph.repo_id = ? AND fph.file_id IN ({file_placeholders})
              AND ce.occurred_at > ?
              AND fph.commit_hash NOT IN ({commit_placeholders})
            """,
            [repo_id, *file_ids, occurred_at, *commit_hashes],
        ).fetchall()
        count = len(rows)

    return count, (STATUS_INCOMPLETE if any_missing else STATUS_COMPLETE)


def compute_releases_since_count(raw_conn: sqlite3.Connection, repo_id: int, occurred_at: str) -> tuple[int | None, str]:
    """How many releases were published after this event — "presence
    across later releases" (CLAUDE.md Section 2's R candidate list),
    mirroring P's `compute_release_proximity` but counting every
    subsequent release instead of finding only the nearest one.

    Deliberately does *not* follow `release_proximity`'s not_applicable
    rule for "no later release exists yet." That rule is right for P's
    question ("how soon did this ship" is genuinely undefined with no
    next release to measure to) but wrong for R's: "how many releases has
    this event lived through" is a well-defined, meaningful zero when
    none have shipped since — a young or recently-changed file legitimately
    hasn't been through any release cycle yet, which is real historical-salience
    information, not a missing value. `not_applicable` is reserved for the
    case the concept genuinely doesn't exist: a repository with zero
    releases in its entire collected history.

    No `incomplete_lower_bound` case: unlike issues/PRs/reviews, release
    collection has no pagination-truncation flag in the Stage 1 schema
    (see `src/collection/schema.py` — no `releases_truncated` column), so
    every collected release is known to be the complete set."""
    total_releases = raw_conn.execute("SELECT COUNT(*) FROM releases WHERE repo_id = ?", (repo_id,)).fetchone()[0]
    if total_releases == 0:
        return None, STATUS_NOT_APPLICABLE

    count = raw_conn.execute(
        "SELECT COUNT(*) FROM releases WHERE repo_id = ? AND published_at > ?", (repo_id, occurred_at)
    ).fetchone()[0]
    return count, STATUS_COMPLETE


def compute_later_references_count(
    raw_conn: sqlite3.Connection, repo_id: int, event_type: str, source_pr_number: int | None, occurred_at: str
) -> tuple[int | None, str]:
    """How many *other* issues/PRs referenced this PR after it concluded —
    "later references" (CLAUDE.md Section 2's R candidate list), from
    GitHub's own `crossReferencedEvent` timeline data (`pr_cross_references`),
    not a text-guessed scan. Chosen over regex-matching PR bodies/comments
    for `#NNN` mentions for the same reason `issue_link_present` uses
    GitHub's `closingIssuesReferences` instead of parsing "fixes #123":
    GitHub's own resolution handles cross-repo references, alternate
    phrasing, and stays authoritative, where a regex would be a guess.

    The "later" filter is not a formality: checked against real
    pallets/markupsafe data before writing this, 41% of collected
    cross-references (30 of 73) happened *before* the target PR's own
    `occurred_at` — active concurrent discussion referencing a PR that
    hasn't merged yet is common, and counting those would conflate
    "discussed at the time" (P territory) with "still being referenced
    afterward" (what R is actually asking).

    Only defined for `pull_request` events — GitHub's cross-reference
    timeline is a PR/issue-level mechanism with no equivalent for a raw
    commit. `incomplete_lower_bound` whenever Stage 1 flagged
    `cross_references_truncated` (more than the collected page of
    references exist) — the same "count from partial evidence is still a
    real floor" reasoning as `files_survived`, regardless of how many (if
    any) of the collected references happen to pass the time filter."""
    if event_type != "pull_request" or source_pr_number is None:
        return None, STATUS_NOT_APPLICABLE

    row = raw_conn.execute(
        "SELECT id, cross_references_truncated FROM pull_requests WHERE repo_id = ? AND number = ?",
        (repo_id, source_pr_number),
    ).fetchone()
    if row is None:
        return None, STATUS_NOT_APPLICABLE
    pr_id, truncated = row

    count = raw_conn.execute(
        "SELECT COUNT(*) FROM pr_cross_references WHERE pr_id = ? AND referenced_at > ?", (pr_id, occurred_at)
    ).fetchone()[0]

    return count, (STATUS_INCOMPLETE if truncated else STATUS_COMPLETE)
