from src.features.p_features import (
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_NOT_APPLICABLE,
    compute_churn,
    compute_comment_count,
    compute_distinct_commenters,
    compute_files_changed,
    compute_issue_has_label,
    compute_issue_link_present,
    compute_reaction_count,
    compute_release_proximity,
    compute_review_rounds,
    compute_reviewer_count,
)


def _insert_pr(conn, number, reviews_truncated=0, review_comments_truncated=0, comments_truncated=0, commits_truncated=0, closing_issues_truncated=0, reaction_count=0):
    conn.execute(
        """
        INSERT INTO pull_requests
            (repo_id, number, title, state, reviews_truncated, commits_truncated, review_comments_truncated, comments_truncated, closing_issues_truncated, reaction_count)
        VALUES (1, ?, 't', 'open', ?, ?, ?, ?, ?, ?)
        """,
        (number, reviews_truncated, commits_truncated, review_comments_truncated, comments_truncated, closing_issues_truncated, reaction_count),
    )
    return conn.execute("SELECT id FROM pull_requests WHERE repo_id=1 AND number=?", (number,)).fetchone()[0]


def _link_closing_issue(conn, pr_id, issue_number):
    conn.execute("INSERT INTO pr_closing_issues (pr_id, issue_number) VALUES (?, ?)", (pr_id, issue_number))


def _insert_issue(conn, number):
    conn.execute(
        "INSERT INTO issues (repo_id, number, title, state) VALUES (1, ?, 't', 'open')",
        (number,),
    )
    return conn.execute("SELECT id FROM issues WHERE repo_id=1 AND number=?", (number,)).fetchone()[0]


def _insert_issue_label(conn, issue_id, label="bug"):
    conn.execute("INSERT INTO issue_labels (issue_id, label) VALUES (?, ?)", (issue_id, label))


def _insert_release(conn, published_at):
    conn.execute(
        "INSERT INTO releases (repo_id, tag_name, published_at) VALUES (1, ?, ?)",
        (published_at, published_at),
    )


def _insert_commit(conn, hash_, insertions=0, deletions=0, files_changed_count=0):
    conn.execute(
        """
        INSERT INTO commits (repo_id, hash, is_merge, insertions, deletions, files_changed_count)
        VALUES (1, ?, 0, ?, ?, ?)
        """,
        (hash_, insertions, deletions, files_changed_count),
    )


def _insert_commit_file(conn, hash_, filename):
    conn.execute(
        "INSERT INTO commit_files (repo_id, commit_hash, filename, change_type) VALUES (1, ?, ?, 'M')",
        (hash_, filename),
    )


def _link_pr_commit(conn, pr_id, hash_):
    conn.execute("INSERT INTO pr_commits (pr_id, commit_hash) VALUES (?, ?)", (pr_id, hash_))


def _insert_pr_comment(conn, pr_id, author_login="x"):
    conn.execute(
        "INSERT INTO pr_comments (pr_id, author_login, created_at, body) VALUES (?, ?, NULL, 'c')",
        (pr_id, author_login),
    )


def _insert_review_comment(conn, pr_id, author_login="x"):
    conn.execute(
        "INSERT INTO pr_review_comments (pr_id, review_id, author_login, created_at, body, path) VALUES (?, NULL, ?, NULL, 'c', NULL)",
        (pr_id, author_login),
    )


def test_comment_count_complete(raw_conn):
    pr_id = _insert_pr(raw_conn, 10)
    _insert_pr_comment(raw_conn, pr_id)
    _insert_pr_comment(raw_conn, pr_id)
    _insert_review_comment(raw_conn, pr_id)
    raw_conn.commit()

    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=10)

    assert value == 3
    assert status == STATUS_COMPLETE


def test_comment_count_true_zero_is_complete_not_missing(raw_conn):
    _insert_pr(raw_conn, 11)
    raw_conn.commit()

    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=11)

    assert value == 0
    assert status == STATUS_COMPLETE


def test_comment_count_incomplete_when_reviews_truncated(raw_conn):
    pr_id = _insert_pr(raw_conn, 12, reviews_truncated=1)
    _insert_pr_comment(raw_conn, pr_id)
    raw_conn.commit()

    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=12)

    assert value == 1
    assert status == STATUS_INCOMPLETE


def test_comment_count_incomplete_when_review_comments_truncated(raw_conn):
    pr_id = _insert_pr(raw_conn, 13, review_comments_truncated=1)
    _insert_review_comment(raw_conn, pr_id)
    raw_conn.commit()

    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=13)

    assert status == STATUS_INCOMPLETE


def test_comment_count_incomplete_when_general_comments_truncated(raw_conn):
    _insert_pr(raw_conn, 14, comments_truncated=1)
    raw_conn.commit()

    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=14)

    assert status == STATUS_INCOMPLETE


def test_comment_count_not_applicable_for_standalone_commit(raw_conn):
    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_comment_count_not_applicable_for_commit_level_event(raw_conn):
    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_comment_count_not_applicable_when_pr_missing_from_raw(raw_conn):
    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=999)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_comment_count_scoped_by_repo_id(raw_conn):
    """A PR #10 in a different repo_id must not be picked up."""
    raw_conn.execute(
        """
        INSERT INTO pull_requests
            (repo_id, number, title, state, reviews_truncated, commits_truncated, review_comments_truncated, comments_truncated)
        VALUES (2, 10, 't', 'open', 0, 0, 0, 0)
        """
    )
    raw_conn.commit()

    value, status = compute_comment_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=10)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


# --- distinct_commenters ---

def test_distinct_commenters_counts_unique_people_not_comments(raw_conn):
    pr_id = _insert_pr(raw_conn, 20)
    _insert_pr_comment(raw_conn, pr_id, author_login="alice")
    _insert_pr_comment(raw_conn, pr_id, author_login="alice")  # same person, second comment
    _insert_review_comment(raw_conn, pr_id, author_login="bob")
    raw_conn.commit()

    value, status = compute_distinct_commenters(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=20)

    assert value == 2  # alice, bob — not 3
    assert status == STATUS_COMPLETE


def test_distinct_commenters_counts_same_person_across_both_channels_once(raw_conn):
    pr_id = _insert_pr(raw_conn, 21)
    _insert_pr_comment(raw_conn, pr_id, author_login="alice")
    _insert_review_comment(raw_conn, pr_id, author_login="alice")
    raw_conn.commit()

    value, status = compute_distinct_commenters(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=21)

    assert value == 1


def test_distinct_commenters_excludes_deleted_ghost_accounts(raw_conn):
    pr_id = _insert_pr(raw_conn, 22)
    _insert_pr_comment(raw_conn, pr_id, author_login="alice")
    _insert_pr_comment(raw_conn, pr_id, author_login=None)  # deleted account
    raw_conn.commit()

    value, status = compute_distinct_commenters(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=22)

    assert value == 1


def test_distinct_commenters_true_zero_is_complete(raw_conn):
    _insert_pr(raw_conn, 23)
    raw_conn.commit()

    value, status = compute_distinct_commenters(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=23)

    assert value == 0
    assert status == STATUS_COMPLETE


def test_distinct_commenters_incomplete_when_truncated(raw_conn):
    pr_id = _insert_pr(raw_conn, 24, reviews_truncated=1)
    _insert_pr_comment(raw_conn, pr_id, author_login="alice")
    raw_conn.commit()

    value, status = compute_distinct_commenters(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=24)

    assert status == STATUS_INCOMPLETE


def test_distinct_commenters_not_applicable_for_standalone_commit(raw_conn):
    value, status = compute_distinct_commenters(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


# --- reviewer_count ---

def _insert_review(conn, pr_id, reviewer_login="x"):
    conn.execute(
        "INSERT INTO pr_reviews (pr_id, reviewer_login, state, submitted_at, body) VALUES (?, ?, 'APPROVED', NULL, NULL)",
        (pr_id, reviewer_login),
    )


def test_reviewer_count_counts_distinct_reviewers(raw_conn):
    pr_id = _insert_pr(raw_conn, 30)
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    _insert_review(raw_conn, pr_id, reviewer_login="alice")  # re-reviewed after changes, still one person
    _insert_review(raw_conn, pr_id, reviewer_login="bob")
    raw_conn.commit()

    value, status = compute_reviewer_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=30)

    assert value == 2
    assert status == STATUS_COMPLETE


def test_reviewer_count_silent_approval_still_counts(raw_conn):
    """A reviewer who approves with no comment body shows up here, unlike
    in distinct_commenters — that's intentional, not a bug."""
    pr_id = _insert_pr(raw_conn, 31)
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    raw_conn.commit()

    value, status = compute_reviewer_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=31)

    assert value == 1


def test_reviewer_count_true_zero_is_complete(raw_conn):
    _insert_pr(raw_conn, 32)
    raw_conn.commit()

    value, status = compute_reviewer_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=32)

    assert value == 0
    assert status == STATUS_COMPLETE


def test_reviewer_count_incomplete_only_when_reviews_truncated(raw_conn):
    pr_id = _insert_pr(raw_conn, 33, reviews_truncated=1)
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    raw_conn.commit()

    value, status = compute_reviewer_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=33)

    assert status == STATUS_INCOMPLETE


def test_reviewer_count_stays_complete_when_only_review_comments_truncated(raw_conn):
    """reviewer_count only reads pr_reviews — a truncated review-comments
    or general-comments channel doesn't affect who's in the reviews list."""
    pr_id = _insert_pr(raw_conn, 34, review_comments_truncated=1, comments_truncated=1)
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    raw_conn.commit()

    value, status = compute_reviewer_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=34)

    assert status == STATUS_COMPLETE


def test_reviewer_count_not_applicable_for_commit_level_event(raw_conn):
    value, status = compute_reviewer_count(raw_conn, repo_id=1, event_type="commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


# --- review_rounds ---

def test_review_rounds_counts_submissions_not_distinct_reviewers(raw_conn):
    pr_id = _insert_pr(raw_conn, 40)
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    raw_conn.commit()

    value, status = compute_review_rounds(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=40)

    assert value == 3  # one person, three separate review submissions
    assert status == STATUS_COMPLETE


def test_review_rounds_true_zero_is_complete(raw_conn):
    _insert_pr(raw_conn, 41)
    raw_conn.commit()

    value, status = compute_review_rounds(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=41)

    assert value == 0
    assert status == STATUS_COMPLETE


def test_review_rounds_incomplete_only_when_reviews_truncated(raw_conn):
    pr_id = _insert_pr(raw_conn, 42, reviews_truncated=1)
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    raw_conn.commit()

    value, status = compute_review_rounds(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=42)

    assert status == STATUS_INCOMPLETE


def test_review_rounds_stays_complete_when_only_comment_channels_truncated(raw_conn):
    pr_id = _insert_pr(raw_conn, 43, review_comments_truncated=1, comments_truncated=1)
    _insert_review(raw_conn, pr_id, reviewer_login="alice")
    raw_conn.commit()

    value, status = compute_review_rounds(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=43)

    assert status == STATUS_COMPLETE


def test_review_rounds_not_applicable_for_standalone_commit(raw_conn):
    value, status = compute_review_rounds(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_files_changed_and_churn_complete_pr_all_commits_found(raw_conn):
    pr_id = _insert_pr(raw_conn, 3030)
    _insert_commit(raw_conn, "c1", insertions=100, deletions=20, files_changed_count=2)
    _insert_commit(raw_conn, "c2", insertions=50, deletions=10, files_changed_count=3)
    _insert_commit_file(raw_conn, "c1", "a.py")
    _insert_commit_file(raw_conn, "c1", "b.py")
    _insert_commit_file(raw_conn, "c2", "b.py")
    _insert_commit_file(raw_conn, "c2", "c.py")
    _link_pr_commit(raw_conn, pr_id, "c1")
    _link_pr_commit(raw_conn, pr_id, "c2")
    raw_conn.commit()

    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=3030)
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=3030)

    assert files_value == 3  # a.py, b.py, c.py — distinct
    assert files_status == STATUS_COMPLETE
    assert churn_value == 180  # 100+20+50+10
    assert churn_status == STATUS_COMPLETE


def test_files_changed_and_churn_incomplete_when_linked_commit_missing_locally(raw_conn):
    # simulates a squash-merge/rebase gap: PR links a commit hash GitHub knows
    # about but that never landed on the default branch, so it's absent from
    # our collected `commits` table even though nothing was truncated.
    pr_id = _insert_pr(raw_conn, 1555)
    _insert_commit(raw_conn, "found1", insertions=10, deletions=5, files_changed_count=1)
    _insert_commit_file(raw_conn, "found1", "a.py")
    _link_pr_commit(raw_conn, pr_id, "found1")
    _link_pr_commit(raw_conn, pr_id, "missing1")
    raw_conn.commit()

    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=1555)
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=1555)

    assert files_value == 1
    assert files_status == STATUS_INCOMPLETE
    assert churn_value == 15
    assert churn_status == STATUS_INCOMPLETE


def test_files_changed_and_churn_incomplete_when_commits_truncated_flag_set(raw_conn):
    # every linked commit is found locally, but the collection layer flagged
    # that not all of the PR's commits were paginated in — still a floor.
    pr_id = _insert_pr(raw_conn, 99, commits_truncated=1)
    _insert_commit(raw_conn, "c1", insertions=1, deletions=1, files_changed_count=1)
    _insert_commit_file(raw_conn, "c1", "a.py")
    _link_pr_commit(raw_conn, pr_id, "c1")
    raw_conn.commit()

    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=99)
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=99)

    assert files_value == 1
    assert files_status == STATUS_INCOMPLETE
    assert churn_value == 2
    assert churn_status == STATUS_INCOMPLETE


def test_files_changed_and_churn_pr_with_no_linked_commits_is_complete_zero(raw_conn):
    pr_id = _insert_pr(raw_conn, 5)
    raw_conn.commit()

    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=5)
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=5)

    assert files_value == 0
    assert files_status == STATUS_COMPLETE
    assert churn_value == 0
    assert churn_status == STATUS_COMPLETE


def test_files_changed_and_churn_not_applicable_when_pr_row_missing(raw_conn):
    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=404)
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=404)

    assert files_value is None
    assert files_status == STATUS_NOT_APPLICABLE
    assert churn_value is None
    assert churn_status == STATUS_NOT_APPLICABLE


def test_files_changed_and_churn_complete_for_standalone_commit(raw_conn):
    _insert_commit(raw_conn, "solo1", insertions=7, deletions=3, files_changed_count=4)
    raw_conn.commit()

    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None, primary_commit_hash="solo1")
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None, primary_commit_hash="solo1")

    assert files_value == 4
    assert files_status == STATUS_COMPLETE
    assert churn_value == 10
    assert churn_status == STATUS_COMPLETE


def test_files_changed_and_churn_complete_for_commit_level_event(raw_conn):
    _insert_commit(raw_conn, "solo2", insertions=1, deletions=1, files_changed_count=1)
    raw_conn.commit()

    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="commit", source_pr_number=None, primary_commit_hash="solo2")
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="commit", source_pr_number=None, primary_commit_hash="solo2")

    assert files_value == 1
    assert files_status == STATUS_COMPLETE
    assert churn_value == 2
    assert churn_status == STATUS_COMPLETE


def test_files_changed_and_churn_not_applicable_without_primary_commit_hash(raw_conn):
    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None, primary_commit_hash=None)
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None, primary_commit_hash=None)

    assert files_value is None
    assert files_status == STATUS_NOT_APPLICABLE
    assert churn_value is None
    assert churn_status == STATUS_NOT_APPLICABLE


def test_files_changed_and_churn_not_applicable_when_commit_row_missing(raw_conn):
    files_value, files_status = compute_files_changed(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None, primary_commit_hash="ghost")
    churn_value, churn_status = compute_churn(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None, primary_commit_hash="ghost")

    assert files_value is None
    assert files_status == STATUS_NOT_APPLICABLE
    assert churn_value is None
    assert churn_status == STATUS_NOT_APPLICABLE


def test_issue_link_present_true_when_pr_has_closing_issue(raw_conn):
    pr_id = _insert_pr(raw_conn, 43)
    _link_closing_issue(raw_conn, pr_id, 26)
    raw_conn.commit()

    value, status = compute_issue_link_present(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=43)

    assert value is True
    assert status == STATUS_COMPLETE


def test_issue_link_present_false_is_complete_not_missing(raw_conn):
    _insert_pr(raw_conn, 2)
    raw_conn.commit()

    value, status = compute_issue_link_present(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=2)

    assert value is False
    assert status == STATUS_COMPLETE


def test_issue_link_present_true_even_when_truncated(raw_conn):
    # truncation means more linked issues exist beyond what we paginated in,
    # but we already found at least one — presence is still a confident True.
    pr_id = _insert_pr(raw_conn, 50, closing_issues_truncated=1)
    _link_closing_issue(raw_conn, pr_id, 1)
    raw_conn.commit()

    value, status = compute_issue_link_present(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=50)

    assert value is True
    assert status == STATUS_COMPLETE


def test_issue_link_present_incomplete_when_truncated_and_none_found(raw_conn):
    _insert_pr(raw_conn, 51, closing_issues_truncated=1)
    raw_conn.commit()

    value, status = compute_issue_link_present(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=51)

    assert status == STATUS_INCOMPLETE


def test_issue_link_present_not_applicable_for_standalone_commit(raw_conn):
    value, status = compute_issue_link_present(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_issue_link_present_not_applicable_for_commit_level_event(raw_conn):
    value, status = compute_issue_link_present(raw_conn, repo_id=1, event_type="commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_issue_link_present_not_applicable_when_pr_missing_from_raw(raw_conn):
    value, status = compute_issue_link_present(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=999)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


# --- issue_has_label ---

def test_issue_has_label_true_when_linked_issue_has_a_label(raw_conn):
    pr_id = _insert_pr(raw_conn, 60)
    issue_id = _insert_issue(raw_conn, 30)
    _insert_issue_label(raw_conn, issue_id, "bug")
    _link_closing_issue(raw_conn, pr_id, 30)
    raw_conn.commit()

    value, status = compute_issue_has_label(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=60)

    assert value is True
    assert status == STATUS_COMPLETE


def test_issue_has_label_false_when_linked_issue_has_no_label(raw_conn):
    pr_id = _insert_pr(raw_conn, 61)
    _insert_issue(raw_conn, 31)
    _link_closing_issue(raw_conn, pr_id, 31)
    raw_conn.commit()

    value, status = compute_issue_has_label(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=61)

    assert value is False
    assert status == STATUS_COMPLETE


def test_issue_has_label_not_applicable_when_no_issue_linked(raw_conn):
    _insert_pr(raw_conn, 62)
    raw_conn.commit()

    value, status = compute_issue_has_label(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=62)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_issue_has_label_incomplete_when_linked_issue_not_found_locally(raw_conn):
    # the issue number is linked but was never itself collected (e.g. a
    # cross-repo reference) — its labels are unknown, not absent.
    pr_id = _insert_pr(raw_conn, 63)
    _link_closing_issue(raw_conn, pr_id, 999)
    raw_conn.commit()

    value, status = compute_issue_has_label(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=63)

    assert value is False
    assert status == STATUS_INCOMPLETE


def test_issue_has_label_true_even_when_one_of_several_linked_issues_unresolved(raw_conn):
    pr_id = _insert_pr(raw_conn, 64)
    issue_id = _insert_issue(raw_conn, 32)
    _insert_issue_label(raw_conn, issue_id, "bug")
    _link_closing_issue(raw_conn, pr_id, 32)
    _link_closing_issue(raw_conn, pr_id, 998)  # unresolved, but doesn't matter — already True
    raw_conn.commit()

    value, status = compute_issue_has_label(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=64)

    assert value is True
    assert status == STATUS_COMPLETE


def test_issue_has_label_incomplete_when_truncated_and_no_label_found(raw_conn):
    pr_id = _insert_pr(raw_conn, 65, closing_issues_truncated=1)
    _insert_issue(raw_conn, 33)
    _link_closing_issue(raw_conn, pr_id, 33)
    raw_conn.commit()

    value, status = compute_issue_has_label(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=65)

    assert value is False
    assert status == STATUS_INCOMPLETE


def test_issue_has_label_not_applicable_for_standalone_commit(raw_conn):
    value, status = compute_issue_has_label(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_issue_has_label_not_applicable_when_pr_missing_from_raw(raw_conn):
    value, status = compute_issue_has_label(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=999)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


# --- release_proximity ---

def test_release_proximity_complete_when_a_later_release_exists(raw_conn):
    _insert_release(raw_conn, "2024-01-10T00:00:00Z")
    _insert_release(raw_conn, "2024-02-01T00:00:00Z")
    raw_conn.commit()

    value, status = compute_release_proximity(
        raw_conn, repo_id=1, event_type="commit", source_pr_number=None,
        occurred_at="2024-01-01T00:00:00Z",
    )

    # nearest later release is 2024-01-10, 9 days = 777600 seconds
    assert value == 777600
    assert status == STATUS_COMPLETE


def test_release_proximity_uses_nearest_not_furthest_later_release(raw_conn):
    _insert_release(raw_conn, "2024-03-01T00:00:00Z")
    _insert_release(raw_conn, "2024-01-02T00:00:00Z")
    raw_conn.commit()

    value, status = compute_release_proximity(
        raw_conn, repo_id=1, event_type="commit", source_pr_number=None,
        occurred_at="2024-01-01T00:00:00Z",
    )

    assert value == 86400  # 1 day to the Jan 2 release, not the March one
    assert status == STATUS_COMPLETE


def test_release_proximity_not_applicable_when_no_release_after_event(raw_conn):
    _insert_release(raw_conn, "2024-01-01T00:00:00Z")
    raw_conn.commit()

    value, status = compute_release_proximity(
        raw_conn, repo_id=1, event_type="commit", source_pr_number=None,
        occurred_at="2024-06-01T00:00:00Z",
    )

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_release_proximity_not_applicable_when_repo_has_no_releases(raw_conn):
    value, status = compute_release_proximity(
        raw_conn, repo_id=1, event_type="commit", source_pr_number=None,
        occurred_at="2024-01-01T00:00:00Z",
    )

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_release_proximity_applies_to_pull_request_events_too(raw_conn):
    _insert_release(raw_conn, "2024-01-15T00:00:00Z")
    raw_conn.commit()

    value, status = compute_release_proximity(
        raw_conn, repo_id=1, event_type="pull_request", source_pr_number=1,
        occurred_at="2024-01-14T00:00:00Z",
    )

    assert value == 86400
    assert status == STATUS_COMPLETE


def test_release_proximity_scoped_by_repo_id(raw_conn):
    raw_conn.execute("INSERT INTO releases (repo_id, tag_name, published_at) VALUES (2, 'v1', '2024-01-02T00:00:00Z')")
    raw_conn.commit()

    value, status = compute_release_proximity(
        raw_conn, repo_id=1, event_type="commit", source_pr_number=None,
        occurred_at="2024-01-01T00:00:00Z",
    )

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


# --- reaction_count ---

def test_reaction_count_complete_nonzero(raw_conn):
    _insert_pr(raw_conn, 70, reaction_count=3)
    raw_conn.commit()

    value, status = compute_reaction_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=70)

    assert value == 3
    assert status == STATUS_COMPLETE


def test_reaction_count_true_zero_is_complete_not_missing(raw_conn):
    _insert_pr(raw_conn, 71)
    raw_conn.commit()

    value, status = compute_reaction_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=71)

    assert value == 0
    assert status == STATUS_COMPLETE


def test_reaction_count_not_applicable_for_standalone_commit(raw_conn):
    value, status = compute_reaction_count(raw_conn, repo_id=1, event_type="standalone_commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_reaction_count_not_applicable_for_commit_level_event(raw_conn):
    value, status = compute_reaction_count(raw_conn, repo_id=1, event_type="commit", source_pr_number=None)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE


def test_reaction_count_not_applicable_when_pr_missing_from_raw(raw_conn):
    value, status = compute_reaction_count(raw_conn, repo_id=1, event_type="pull_request", source_pr_number=999)

    assert value is None
    assert status == STATUS_NOT_APPLICABLE
