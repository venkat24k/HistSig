from src.features.storage import insert_p_features


def _insert_event(conn, event_id, repo_id):
    conn.execute(
        """
        INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at)
        VALUES (?, ?, 'commit_level', 'commit', NULL, 'abc', 't', '2024-01-01')
        """,
        (event_id, repo_id),
    )
    conn.commit()


def _row(event_id, comment_count=3, comment_count_status="complete", distinct_commenters=2, distinct_commenters_status="complete",
         reviewer_count=1, reviewer_count_status="complete", review_rounds=1, review_rounds_status="complete",
         files_changed=4, files_changed_status="complete", churn=100, churn_status="complete",
         issue_link_present=True, issue_link_present_status="complete",
         issue_has_label=True, issue_has_label_status="complete",
         release_proximity=86400, release_proximity_status="complete",
         reaction_count=2, reaction_count_status="complete"):
    return {
        "event_id": event_id,
        "comment_count": comment_count,
        "comment_count_status": comment_count_status,
        "distinct_commenters": distinct_commenters,
        "distinct_commenters_status": distinct_commenters_status,
        "reviewer_count": reviewer_count,
        "reviewer_count_status": reviewer_count_status,
        "review_rounds": review_rounds,
        "review_rounds_status": review_rounds_status,
        "files_changed": files_changed,
        "files_changed_status": files_changed_status,
        "churn": churn,
        "churn_status": churn_status,
        "issue_link_present": issue_link_present,
        "issue_link_present_status": issue_link_present_status,
        "issue_has_label": issue_has_label,
        "issue_has_label_status": issue_has_label_status,
        "release_proximity": release_proximity,
        "release_proximity_status": release_proximity_status,
        "reaction_count": reaction_count,
        "reaction_count_status": reaction_count_status,
    }


def test_insert_p_features_is_idempotent(processed_conn):
    _insert_event(processed_conn, 1, repo_id=1)
    rows = [_row(1)]
    insert_p_features(processed_conn, repo_id=1, rows=rows)
    insert_p_features(processed_conn, repo_id=1, rows=rows)

    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_features").fetchone()[0] == 1
    row = processed_conn.execute(
        "SELECT comment_count, comment_count_status, distinct_commenters, distinct_commenters_status FROM event_p_features WHERE event_id=1"
    ).fetchone()
    assert row == (3, "complete", 2, "complete")


def test_insert_p_features_stores_null_for_not_applicable(processed_conn):
    _insert_event(processed_conn, 1, repo_id=1)
    rows = [_row(1, comment_count=None, comment_count_status="not_applicable", distinct_commenters=None, distinct_commenters_status="not_applicable")]
    insert_p_features(processed_conn, repo_id=1, rows=rows)

    row = processed_conn.execute("SELECT comment_count, comment_count_status FROM event_p_features WHERE event_id=1").fetchone()
    assert row == (None, "not_applicable")


def test_insert_p_features_does_not_clobber_other_repo(processed_conn):
    _insert_event(processed_conn, 1, repo_id=1)
    _insert_event(processed_conn, 2, repo_id=2)
    insert_p_features(processed_conn, repo_id=1, rows=[_row(1, comment_count=1)])
    insert_p_features(processed_conn, repo_id=2, rows=[_row(2, comment_count=2)])

    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_features").fetchone()[0] == 2

    insert_p_features(processed_conn, repo_id=1, rows=[_row(1, comment_count=9)])
    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_features").fetchone()[0] == 2
    assert processed_conn.execute("SELECT comment_count FROM event_p_features WHERE event_id=2").fetchone()[0] == 2
