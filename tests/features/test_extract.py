from src.features.extract import extract_p_features


def _insert_pr(conn, number):
    conn.execute(
        """
        INSERT INTO pull_requests
            (repo_id, number, title, state, reviews_truncated, commits_truncated, review_comments_truncated, comments_truncated)
        VALUES (1, ?, 't', 'open', 0, 0, 0, 0)
        """,
        (number,),
    )
    return conn.execute("SELECT id FROM pull_requests WHERE repo_id=1 AND number=?", (number,)).fetchone()[0]


def test_extract_p_features_end_to_end(raw_conn, processed_conn):
    pr_id = _insert_pr(raw_conn, 10)
    raw_conn.execute("INSERT INTO pr_comments (pr_id, author_login, created_at, body) VALUES (?, 'x', NULL, 'c')", (pr_id,))
    raw_conn.commit()

    processed_conn.execute(
        """
        INSERT INTO candidate_events (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at)
        VALUES (1, 'pr_bundle', 'pull_request', 10, NULL, 't', '2024-01-01')
        """
    )
    processed_conn.execute(
        """
        INSERT INTO candidate_events (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at)
        VALUES (1, 'pr_bundle', 'standalone_commit', NULL, 'abc123', 't', '2024-01-01')
        """
    )
    processed_conn.commit()

    summary = extract_p_features(raw_conn, processed_conn, repo_id=1)

    assert summary["events_processed"] == 2
    assert summary["comment_count_by_status"] == {"complete": 1, "not_applicable": 1}
    assert summary["distinct_commenters_by_status"] == {"complete": 1, "not_applicable": 1}
    assert summary["reviewer_count_by_status"] == {"complete": 1, "not_applicable": 1}
    assert summary["review_rounds_by_status"] == {"complete": 1, "not_applicable": 1}
    assert summary["files_changed_by_status"] == {"complete": 1, "not_applicable": 1}
    assert summary["churn_by_status"] == {"complete": 1, "not_applicable": 1}
    assert summary["issue_link_present_by_status"] == {"complete": 1, "not_applicable": 1}
    assert summary["issue_has_label_by_status"] == {"not_applicable": 2}
    assert summary["release_proximity_by_status"] == {"not_applicable": 2}
    assert summary["reaction_count_by_status"] == {"complete": 1, "not_applicable": 1}

    pr_event_id = processed_conn.execute("SELECT id FROM candidate_events WHERE event_type='pull_request'").fetchone()[0]
    row = processed_conn.execute(
        """
        SELECT comment_count, comment_count_status, distinct_commenters, distinct_commenters_status,
               reviewer_count, reviewer_count_status, review_rounds, review_rounds_status,
               files_changed, files_changed_status, churn, churn_status,
               issue_link_present, issue_link_present_status,
               issue_has_label, issue_has_label_status, release_proximity, release_proximity_status,
               reaction_count, reaction_count_status
        FROM event_p_features WHERE event_id=?
        """,
        (pr_event_id,),
    ).fetchone()
    assert row == (
        1, "complete", 1, "complete", 0, "complete", 0, "complete", 0, "complete", 0, "complete", 0, "complete",
        None, "not_applicable", None, "not_applicable", 0, "complete",
    )

    commit_event_id = processed_conn.execute("SELECT id FROM candidate_events WHERE event_type='standalone_commit'").fetchone()[0]
    row = processed_conn.execute(
        """
        SELECT comment_count, comment_count_status, distinct_commenters, distinct_commenters_status,
               reviewer_count, reviewer_count_status, review_rounds, review_rounds_status,
               files_changed, files_changed_status, churn, churn_status,
               issue_link_present, issue_link_present_status,
               issue_has_label, issue_has_label_status, release_proximity, release_proximity_status,
               reaction_count, reaction_count_status
        FROM event_p_features WHERE event_id=?
        """,
        (commit_event_id,),
    ).fetchone()
    assert row == (
        None, "not_applicable", None, "not_applicable", None, "not_applicable", None, "not_applicable",
        None, "not_applicable", None, "not_applicable", None, "not_applicable",
        None, "not_applicable", None, "not_applicable", None, "not_applicable",
    )


def test_extract_p_features_is_idempotent(raw_conn, processed_conn):
    processed_conn.execute(
        """
        INSERT INTO candidate_events (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at)
        VALUES (1, 'commit_level', 'commit', NULL, 'abc123', 't', '2024-01-01')
        """
    )
    processed_conn.commit()

    extract_p_features(raw_conn, processed_conn, repo_id=1)
    extract_p_features(raw_conn, processed_conn, repo_id=1)

    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_features").fetchone()[0] == 1
