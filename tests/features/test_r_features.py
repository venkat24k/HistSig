import pytest

from src.features.r_features import (
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_NOT_APPLICABLE,
    build_file_touch_index,
    compute_files_survived,
    compute_later_references_count,
    compute_maturity,
    compute_releases_since_count,
    compute_subsequent_modification_count,
)


def _insert_event(conn, event_id, repo_id=1, occurred_at="2020-01-01T00:00:00Z"):
    conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, 'commit_level', 'commit', NULL, 'x', 't', ?)",
        (event_id, repo_id, occurred_at),
    )


def _insert_commit_level_event(conn, event_id, commit_hash, occurred_at, repo_id=1):
    """A *different* commit's own commit_level event — this is what
    compute_subsequent_modification_count joins against to find a
    candidate later commit's date."""
    conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, 'commit_level', 'commit', NULL, ?, 't', ?)",
        (event_id, repo_id, commit_hash, occurred_at),
    )


def _link_event_commit(conn, event_id, commit_hash):
    conn.execute("INSERT INTO event_commits (event_id, commit_hash) VALUES (?, ?)", (event_id, commit_hash))


def _insert_file_identity(conn, repo_id, first_path, last_path=None, is_deleted=0):
    conn.execute(
        "INSERT INTO file_identities (repo_id, first_path, last_path, is_deleted) VALUES (?, ?, ?, ?)",
        (repo_id, first_path, last_path or first_path, is_deleted),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_file_path_history(conn, repo_id, commit_hash, path, change_type, file_id):
    conn.execute(
        "INSERT INTO file_path_history (repo_id, commit_hash, path, change_type, file_id) VALUES (?, ?, ?, ?, ?)",
        (repo_id, commit_hash, path, change_type, file_id),
    )


def _insert_commit_annotation(conn, repo_id, commit_hash):
    """Marks a commit_hash as genuinely known/collected (commit_annotations
    is populated for every raw commit regardless of whether it touched any
    files — see normalize.py) — this is what distinguishes a commit that's
    known-but-fileless (a merge commit, a real complete zero) from one
    that's truly missing from local history (an evidence gap)."""
    conn.execute(
        "INSERT INTO commit_annotations (repo_id, commit_hash, contributor_id, is_revert) VALUES (?, ?, NULL, 0)",
        (repo_id, commit_hash),
    )


def _set_availability(conn, repo_id, earliest, latest):
    conn.execute(
        "INSERT INTO repository_data_availability (repo_id, has_releases, has_pr_reviews, has_issues, earliest_commit_date, latest_commit_date, normalized_at) "
        "VALUES (?, 0, 0, 0, ?, ?, ?)",
        (repo_id, earliest, latest, latest),
    )


# --- maturity ---

def test_maturity_hand_computed_example():
    # 15-day window; event 5 days after the earliest commit -> 10 days of
    # the window remain after it -> maturity = 10/15
    value, status = compute_maturity("2020-01-01T00:00:00Z", "2020-01-16T00:00:00Z", "2020-01-06T00:00:00Z")

    assert value == pytest.approx(10 / 15)
    assert status == STATUS_COMPLETE


def test_maturity_is_one_at_the_earliest_commit():
    value, status = compute_maturity("2020-01-01T00:00:00Z", "2020-01-16T00:00:00Z", "2020-01-01T00:00:00Z")

    assert value == pytest.approx(1.0)
    assert status == STATUS_COMPLETE


def test_maturity_is_zero_at_the_latest_commit():
    value, status = compute_maturity("2020-01-01T00:00:00Z", "2020-01-16T00:00:00Z", "2020-01-16T00:00:00Z")

    assert value == pytest.approx(0.0)
    assert status == STATUS_COMPLETE


def test_maturity_not_applicable_when_availability_missing():
    value, status = compute_maturity(None, None, "2020-01-06T00:00:00Z")

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_maturity_not_applicable_when_window_is_zero():
    value, status = compute_maturity("2020-01-01T00:00:00Z", "2020-01-01T00:00:00Z", "2020-01-01T00:00:00Z")

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_maturity_not_applicable_when_occurred_at_is_after_latest_commit():
    # Regression test: a pull_request event's occurred_at (created/closed
    # date) can fall after latest_commit_date when the PR never merged any
    # commits (e.g. still open, or closed unmerged) — verified against
    # real pallets/markupsafe data, where 12 such PRs produced a negative
    # maturity before this guard was added.
    value, status = compute_maturity("2020-01-01T00:00:00Z", "2020-01-16T00:00:00Z", "2020-01-20T00:00:00Z")

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_maturity_not_applicable_when_occurred_at_is_before_earliest_commit():
    value, status = compute_maturity("2020-01-01T00:00:00Z", "2020-01-16T00:00:00Z", "2019-12-01T00:00:00Z")

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


# --- files_survived ---

def test_files_survived_hand_computed_mixed_example(processed_conn):
    # Mirrors the real pallets/markupsafe first-commit worked example: 8
    # files touched by one commit, 2 later deleted, 6 still alive.
    _insert_event(processed_conn, 1)
    _link_event_commit(processed_conn, 1, "c1")
    _insert_commit_annotation(processed_conn, 1, "c1")

    alive_paths = [".gitignore", "MANIFEST.in", "markupsafe/__init__.py", "markupsafe/_native.py", "markupsafe/_speedups.c", "setup.py"]
    deleted_paths = ["LICENSE", "markupsafe/_constants.py"]
    for p in alive_paths:
        fid = _insert_file_identity(processed_conn, 1, p, is_deleted=0)
        _insert_file_path_history(processed_conn, 1, "c1", p, "ADD", fid)
    for p in deleted_paths:
        fid = _insert_file_identity(processed_conn, 1, p, is_deleted=1)
        _insert_file_path_history(processed_conn, 1, "c1", p, "ADD", fid)
    processed_conn.commit()

    value, status = compute_files_survived(processed_conn, repo_id=1, event_id=1)

    assert value == 6
    assert status == STATUS_COMPLETE


def test_files_survived_all_deleted_is_a_real_zero(processed_conn):
    _insert_event(processed_conn, 1)
    _link_event_commit(processed_conn, 1, "c1")
    _insert_commit_annotation(processed_conn, 1, "c1")
    fid = _insert_file_identity(processed_conn, 1, "dead.py", is_deleted=1)
    _insert_file_path_history(processed_conn, 1, "c1", "dead.py", "ADD", fid)
    processed_conn.commit()

    value, status = compute_files_survived(processed_conn, repo_id=1, event_id=1)

    assert value == 0
    assert status == STATUS_COMPLETE


def test_files_survived_merge_commit_with_no_files_is_a_real_complete_zero(processed_conn):
    # Regression test: ~37% of pallets/markupsafe's commits are merges with
    # zero commit_files rows (PyDriller doesn't diff merges by default).
    # That commit is genuinely known/collected (in commit_annotations) —
    # it just touched nothing — so this must be `complete`, not
    # `incomplete_lower_bound`. An earlier version of this function
    # checked `file_path_history` directly for "is this commit missing"
    # and wrongly flagged every one of these as incomplete.
    _insert_event(processed_conn, 1)
    _link_event_commit(processed_conn, 1, "merge1")
    _insert_commit_annotation(processed_conn, 1, "merge1")
    processed_conn.commit()

    value, status = compute_files_survived(processed_conn, repo_id=1, event_id=1)

    assert value == 0
    assert status == STATUS_COMPLETE


def test_files_survived_incomplete_when_a_linked_commit_is_missing(processed_conn):
    # event links two commits; only one is known at all (in
    # commit_annotations) — the other is a genuine squash-merge-style gap,
    # same as P's files_changed, not merely fileless.
    _insert_event(processed_conn, 1)
    _link_event_commit(processed_conn, 1, "found")
    _link_event_commit(processed_conn, 1, "missing")
    _insert_commit_annotation(processed_conn, 1, "found")
    fid = _insert_file_identity(processed_conn, 1, "alive.py", is_deleted=0)
    _insert_file_path_history(processed_conn, 1, "found", "alive.py", "ADD", fid)
    processed_conn.commit()

    value, status = compute_files_survived(processed_conn, repo_id=1, event_id=1)

    assert value == 1
    assert status == STATUS_INCOMPLETE


def test_files_survived_incomplete_zero_when_no_linked_commit_found_at_all(processed_conn):
    _insert_event(processed_conn, 1)
    _link_event_commit(processed_conn, 1, "missing")
    processed_conn.commit()

    value, status = compute_files_survived(processed_conn, repo_id=1, event_id=1)

    assert value == 0
    assert status == STATUS_INCOMPLETE


def test_files_survived_not_applicable_when_event_has_no_linked_commits(processed_conn):
    _insert_event(processed_conn, 1)
    processed_conn.commit()

    value, status = compute_files_survived(processed_conn, repo_id=1, event_id=1)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_files_survived_counts_each_file_identity_once_even_with_multiple_commits(processed_conn):
    # the same file touched by two of the event's commits must not be
    # double-counted.
    _insert_event(processed_conn, 1)
    _link_event_commit(processed_conn, 1, "c1")
    _link_event_commit(processed_conn, 1, "c2")
    _insert_commit_annotation(processed_conn, 1, "c1")
    _insert_commit_annotation(processed_conn, 1, "c2")
    fid = _insert_file_identity(processed_conn, 1, "alive.py", is_deleted=0)
    _insert_file_path_history(processed_conn, 1, "c1", "alive.py", "ADD", fid)
    _insert_file_path_history(processed_conn, 1, "c2", "alive.py", "MODIFY", fid)
    processed_conn.commit()

    value, status = compute_files_survived(processed_conn, repo_id=1, event_id=1)

    assert value == 1
    assert status == STATUS_COMPLETE


# --- subsequent_modification_count ---

def test_subsequent_modification_count_only_counts_later_touches(processed_conn):
    # file A touched by: an earlier commit, the event's own commit, and a
    # later commit -- only the later one should count.
    _insert_event(processed_conn, 1, occurred_at="2020-06-01T00:00:00Z")
    _link_event_commit(processed_conn, 1, "own1")
    _insert_commit_annotation(processed_conn, 1, "own1")
    fid = _insert_file_identity(processed_conn, 1, "a.py", is_deleted=0)
    _insert_file_path_history(processed_conn, 1, "earlier", "a.py", "ADD", fid)
    _insert_file_path_history(processed_conn, 1, "own1", "a.py", "MODIFY", fid)
    _insert_file_path_history(processed_conn, 1, "later", "a.py", "MODIFY", fid)
    _insert_commit_level_event(processed_conn, 101, "earlier", "2020-01-01T00:00:00Z")
    _insert_commit_level_event(processed_conn, 102, "later", "2020-12-01T00:00:00Z")
    processed_conn.commit()

    value, status = compute_subsequent_modification_count(processed_conn, repo_id=1, event_id=1, occurred_at="2020-06-01T00:00:00Z")

    assert value == 1
    assert status == STATUS_COMPLETE


def test_subsequent_modification_count_counts_distinct_commits_not_distinct_touches(processed_conn):
    # event touches files A and B; ONE later commit touches both -- must
    # count once, not twice.
    _insert_event(processed_conn, 1, occurred_at="2020-06-01T00:00:00Z")
    _link_event_commit(processed_conn, 1, "own1")
    _insert_commit_annotation(processed_conn, 1, "own1")
    fid_a = _insert_file_identity(processed_conn, 1, "a.py", is_deleted=0)
    fid_b = _insert_file_identity(processed_conn, 1, "b.py", is_deleted=0)
    _insert_file_path_history(processed_conn, 1, "own1", "a.py", "ADD", fid_a)
    _insert_file_path_history(processed_conn, 1, "own1", "b.py", "ADD", fid_b)
    _insert_file_path_history(processed_conn, 1, "later", "a.py", "MODIFY", fid_a)
    _insert_file_path_history(processed_conn, 1, "later", "b.py", "MODIFY", fid_b)
    _insert_commit_level_event(processed_conn, 101, "later", "2020-12-01T00:00:00Z")
    processed_conn.commit()

    value, status = compute_subsequent_modification_count(processed_conn, repo_id=1, event_id=1, occurred_at="2020-06-01T00:00:00Z")

    assert value == 1
    assert status == STATUS_COMPLETE


def test_subsequent_modification_count_zero_when_nothing_later(processed_conn):
    _insert_event(processed_conn, 1, occurred_at="2020-06-01T00:00:00Z")
    _link_event_commit(processed_conn, 1, "own1")
    _insert_commit_annotation(processed_conn, 1, "own1")
    fid = _insert_file_identity(processed_conn, 1, "a.py", is_deleted=0)
    _insert_file_path_history(processed_conn, 1, "own1", "a.py", "ADD", fid)
    _insert_file_path_history(processed_conn, 1, "earlier", "a.py", "ADD", fid)
    _insert_commit_level_event(processed_conn, 101, "earlier", "2020-01-01T00:00:00Z")
    processed_conn.commit()

    value, status = compute_subsequent_modification_count(processed_conn, repo_id=1, event_id=1, occurred_at="2020-06-01T00:00:00Z")

    assert value == 0
    assert status == STATUS_COMPLETE


def test_subsequent_modification_count_excludes_own_commits_even_if_dated_later(processed_conn):
    # a multi-commit pull_request-style event whose own occurred_at
    # (merged_at) predates one of its OWN commits' authored date -- that
    # commit must still never count as a "later modification" of itself.
    _insert_event(processed_conn, 1, occurred_at="2020-06-01T00:00:00Z")
    _link_event_commit(processed_conn, 1, "own1")
    _link_event_commit(processed_conn, 1, "own2")
    _insert_commit_annotation(processed_conn, 1, "own1")
    _insert_commit_annotation(processed_conn, 1, "own2")
    fid = _insert_file_identity(processed_conn, 1, "a.py", is_deleted=0)
    _insert_file_path_history(processed_conn, 1, "own1", "a.py", "ADD", fid)
    _insert_file_path_history(processed_conn, 1, "own2", "a.py", "MODIFY", fid)
    # own2's own commit_level event is dated AFTER the PR-style event's occurred_at
    _insert_commit_level_event(processed_conn, 101, "own2", "2020-06-02T00:00:00Z")
    processed_conn.commit()

    value, status = compute_subsequent_modification_count(processed_conn, repo_id=1, event_id=1, occurred_at="2020-06-01T00:00:00Z")

    assert value == 0
    assert status == STATUS_COMPLETE


def test_subsequent_modification_count_incomplete_when_a_linked_commit_is_missing(processed_conn):
    _insert_event(processed_conn, 1, occurred_at="2020-06-01T00:00:00Z")
    _link_event_commit(processed_conn, 1, "found")
    _link_event_commit(processed_conn, 1, "missing")
    _insert_commit_annotation(processed_conn, 1, "found")
    fid = _insert_file_identity(processed_conn, 1, "a.py", is_deleted=0)
    _insert_file_path_history(processed_conn, 1, "found", "a.py", "ADD", fid)
    _insert_file_path_history(processed_conn, 1, "later", "a.py", "MODIFY", fid)
    _insert_commit_level_event(processed_conn, 101, "later", "2020-12-01T00:00:00Z")
    processed_conn.commit()

    value, status = compute_subsequent_modification_count(processed_conn, repo_id=1, event_id=1, occurred_at="2020-06-01T00:00:00Z")

    assert value == 1
    assert status == STATUS_INCOMPLETE


def test_subsequent_modification_count_not_applicable_when_no_linked_commits(processed_conn):
    _insert_event(processed_conn, 1)
    processed_conn.commit()

    value, status = compute_subsequent_modification_count(processed_conn, repo_id=1, event_id=1, occurred_at="2020-01-01T00:00:00Z")

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_subsequent_modification_count_index_path_matches_query_path(processed_conn):
    # Same fixture as the "counts distinct commits" test above, but checked
    # through both the default (query-per-call) path and the precomputed
    # file_touch_index fast path used by extract_r_features -- they must
    # agree exactly.
    _insert_event(processed_conn, 1, occurred_at="2020-06-01T00:00:00Z")
    _link_event_commit(processed_conn, 1, "own1")
    _insert_commit_annotation(processed_conn, 1, "own1")
    fid_a = _insert_file_identity(processed_conn, 1, "a.py", is_deleted=0)
    fid_b = _insert_file_identity(processed_conn, 1, "b.py", is_deleted=0)
    _insert_file_path_history(processed_conn, 1, "own1", "a.py", "ADD", fid_a)
    _insert_file_path_history(processed_conn, 1, "own1", "b.py", "ADD", fid_b)
    _insert_file_path_history(processed_conn, 1, "later1", "a.py", "MODIFY", fid_a)
    _insert_file_path_history(processed_conn, 1, "later2", "b.py", "MODIFY", fid_b)
    _insert_file_path_history(processed_conn, 1, "earlier", "a.py", "MODIFY", fid_a)
    _insert_commit_level_event(processed_conn, 101, "later1", "2020-12-01T00:00:00Z")
    _insert_commit_level_event(processed_conn, 102, "later2", "2020-12-02T00:00:00Z")
    _insert_commit_level_event(processed_conn, 103, "earlier", "2020-01-01T00:00:00Z")
    processed_conn.commit()

    query_value, query_status = compute_subsequent_modification_count(processed_conn, repo_id=1, event_id=1, occurred_at="2020-06-01T00:00:00Z")

    index = build_file_touch_index(processed_conn, repo_id=1)
    indexed_value, indexed_status = compute_subsequent_modification_count(
        processed_conn, repo_id=1, event_id=1, occurred_at="2020-06-01T00:00:00Z", file_touch_index=index
    )

    assert query_value == indexed_value == 2
    assert query_status == indexed_status == STATUS_COMPLETE


# --- releases_since_count ---

def _insert_release(conn, repo_id, tag_name, published_at):
    conn.execute(
        "INSERT INTO releases (repo_id, tag_name, published_at) VALUES (?, ?, ?)",
        (repo_id, tag_name, published_at),
    )


def test_releases_since_count_hand_computed_example(raw_conn):
    _insert_release(raw_conn, 1, "v1.0", "2020-02-01T00:00:00Z")
    _insert_release(raw_conn, 1, "v1.1", "2020-03-01T00:00:00Z")
    _insert_release(raw_conn, 1, "v0.9", "2019-12-01T00:00:00Z")  # before the event
    raw_conn.commit()

    value, status = compute_releases_since_count(raw_conn, repo_id=1, occurred_at="2020-01-01T00:00:00Z")

    assert value == 2
    assert status == STATUS_COMPLETE


def test_releases_since_count_zero_is_complete_not_missing(raw_conn):
    # repo has releases, but none after this (very recent) event -- a real,
    # meaningful zero, not a gap.
    _insert_release(raw_conn, 1, "v1.0", "2020-01-01T00:00:00Z")
    raw_conn.commit()

    value, status = compute_releases_since_count(raw_conn, repo_id=1, occurred_at="2020-06-01T00:00:00Z")

    assert value == 0
    assert status == STATUS_COMPLETE


def test_releases_since_count_not_applicable_when_repo_has_no_releases(raw_conn):
    value, status = compute_releases_since_count(raw_conn, repo_id=1, occurred_at="2020-01-01T00:00:00Z")

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_releases_since_count_scoped_by_repo_id(raw_conn):
    raw_conn.execute("INSERT INTO releases (repo_id, tag_name, published_at) VALUES (2, 'v1.0', '2020-06-01T00:00:00Z')")
    raw_conn.commit()

    value, status = compute_releases_since_count(raw_conn, repo_id=1, occurred_at="2020-01-01T00:00:00Z")

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


# --- later_references_count ---

def _insert_pr(conn, repo_id, number, cross_references_truncated=0):
    conn.execute(
        "INSERT INTO pull_requests (repo_id, number, title, state, cross_references_truncated) VALUES (?, ?, 't', 'open', ?)",
        (repo_id, number, cross_references_truncated),
    )
    return conn.execute("SELECT id FROM pull_requests WHERE repo_id=? AND number=?", (repo_id, number)).fetchone()[0]


def _insert_cross_reference(conn, pr_id, source_number, referenced_at):
    conn.execute(
        "INSERT INTO pr_cross_references (pr_id, source_number, referenced_at) VALUES (?, ?, ?)",
        (pr_id, source_number, referenced_at),
    )


def test_later_references_count_hand_computed_example(raw_conn):
    # Mirrors the real pallets/markupsafe PR #438 worked example: 5
    # cross-references, all strictly after occurred_at.
    pr_id = _insert_pr(raw_conn, 1, 438)
    for src, when in [(494, "2025-05-29T02:51:30Z"), (495, "2025-05-26T22:57:47Z"), (519, "2026-03-10T19:21:54Z"),
                       (523, "2026-05-28T10:47:30Z"), (528, "2026-07-22T11:56:45Z")]:
        _insert_cross_reference(raw_conn, pr_id, src, when)
    raw_conn.commit()

    value, status = compute_later_references_count(
        raw_conn, repo_id=1, event_type="pull_request", source_pr_number=438, occurred_at="2024-04-22T23:50:32Z"
    )

    assert value == 5
    assert status == STATUS_COMPLETE


def test_later_references_count_excludes_references_before_occurred_at(raw_conn):
    # Mirrors the real PR #495 worked example: one cross-reference exists,
    # but it happened before the PR's own occurred_at -- doesn't count.
    pr_id = _insert_pr(raw_conn, 1, 495)
    _insert_cross_reference(raw_conn, pr_id, 494, "2025-05-26T18:53:38Z")
    raw_conn.commit()

    value, status = compute_later_references_count(
        raw_conn, repo_id=1, event_type="pull_request", source_pr_number=495, occurred_at="2025-05-29T03:54:13Z"
    )

    assert value == 0
    assert status == STATUS_COMPLETE


def test_later_references_count_true_zero_when_none_at_all(raw_conn):
    _insert_pr(raw_conn, 1, 2)
    raw_conn.commit()

    value, status = compute_later_references_count(
        raw_conn, repo_id=1, event_type="pull_request", source_pr_number=2, occurred_at="2020-01-01T00:00:00Z"
    )

    assert value == 0
    assert status == STATUS_COMPLETE


def test_later_references_count_incomplete_when_truncated(raw_conn):
    pr_id = _insert_pr(raw_conn, 1, 10, cross_references_truncated=1)
    _insert_cross_reference(raw_conn, pr_id, 20, "2024-06-01T00:00:00Z")
    raw_conn.commit()

    value, status = compute_later_references_count(
        raw_conn, repo_id=1, event_type="pull_request", source_pr_number=10, occurred_at="2024-01-01T00:00:00Z"
    )

    assert value == 1
    assert status == STATUS_INCOMPLETE


def test_later_references_count_not_applicable_for_standalone_commit(raw_conn):
    value, status = compute_later_references_count(
        raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None, occurred_at="2024-01-01T00:00:00Z"
    )

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_later_references_count_not_applicable_when_pr_missing_from_raw(raw_conn):
    value, status = compute_later_references_count(
        raw_conn, repo_id=1, event_type="pull_request", source_pr_number=999, occurred_at="2024-01-01T00:00:00Z"
    )

    assert value is None
    assert status == STATUS_NOT_APPLICABLE
