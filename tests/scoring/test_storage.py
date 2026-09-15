from src.scoring.storage import insert_p_scores, insert_r_scores


def _insert_event(conn, event_id, repo_id=1):
    conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, 'pr_bundle', 'pull_request', NULL, NULL, 't', '2024-01-01')",
        (event_id, repo_id),
    )
    conn.commit()


def test_insert_p_scores_is_idempotent(processed_conn):
    _insert_event(processed_conn, 1)
    score_rows = [(1, 1, "pr_bundle", "pull_request", 0.9, 3, 1)]
    threshold_rows = [(1, "pr_bundle", "pull_request", 0.1, 0.9, 1)]

    insert_p_scores(processed_conn, 1, score_rows, threshold_rows)
    insert_p_scores(processed_conn, 1, score_rows, threshold_rows)

    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_scores").fetchone()[0] == 1
    assert processed_conn.execute("SELECT COUNT(*) FROM p_score_thresholds").fetchone()[0] == 1
    row = processed_conn.execute("SELECT p_score, is_high_p FROM event_p_scores WHERE event_id=1").fetchone()
    assert row == (0.9, 1)


def test_insert_p_scores_stores_null_score_and_null_is_high_p(processed_conn):
    _insert_event(processed_conn, 1)
    insert_p_scores(processed_conn, 1, [(1, 1, "pr_bundle", "pull_request", None, 0, None)], [(1, "pr_bundle", "pull_request", 0.1, None, 0)])

    row = processed_conn.execute("SELECT p_score, features_used, is_high_p FROM event_p_scores WHERE event_id=1").fetchone()
    assert row == (None, 0, None)


def test_insert_p_scores_does_not_clobber_other_repo(processed_conn):
    _insert_event(processed_conn, 1, repo_id=1)
    _insert_event(processed_conn, 2, repo_id=2)
    insert_p_scores(processed_conn, 1, [(1, 1, "pr_bundle", "pull_request", 0.5, 1, 0)], [(1, "pr_bundle", "pull_request", 0.1, 0.9, 1)])
    insert_p_scores(processed_conn, 2, [(2, 2, "pr_bundle", "pull_request", 0.7, 1, 1)], [(2, "pr_bundle", "pull_request", 0.1, 0.7, 1)])

    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_scores").fetchone()[0] == 2

    insert_p_scores(processed_conn, 1, [(1, 1, "pr_bundle", "pull_request", 0.99, 1, 1)], [(1, "pr_bundle", "pull_request", 0.1, 0.99, 1)])

    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_scores").fetchone()[0] == 2
    assert processed_conn.execute("SELECT p_score FROM event_p_scores WHERE event_id=2").fetchone()[0] == 0.7


def test_insert_r_scores_is_idempotent(processed_conn):
    _insert_event(processed_conn, 1)
    score_rows = [(1, 1, "pr_bundle", "pull_request", 0.9, 3, 1)]
    threshold_rows = [(1, "pr_bundle", "pull_request", 0.1, 0.9, 1)]

    insert_r_scores(processed_conn, 1, score_rows, threshold_rows)
    insert_r_scores(processed_conn, 1, score_rows, threshold_rows)

    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_scores").fetchone()[0] == 1
    assert processed_conn.execute("SELECT COUNT(*) FROM r_score_thresholds").fetchone()[0] == 1
    row = processed_conn.execute("SELECT r_score, is_high_r FROM event_r_scores WHERE event_id=1").fetchone()
    assert row == (0.9, 1)


def test_insert_r_scores_does_not_clobber_other_repo(processed_conn):
    _insert_event(processed_conn, 1, repo_id=1)
    _insert_event(processed_conn, 2, repo_id=2)
    insert_r_scores(processed_conn, 1, [(1, 1, "pr_bundle", "pull_request", 0.5, 1, 0)], [(1, "pr_bundle", "pull_request", 0.1, 0.9, 1)])
    insert_r_scores(processed_conn, 2, [(2, 2, "pr_bundle", "pull_request", 0.7, 1, 1)], [(2, "pr_bundle", "pull_request", 0.1, 0.7, 1)])

    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_scores").fetchone()[0] == 2

    insert_r_scores(processed_conn, 1, [(1, 1, "pr_bundle", "pull_request", 0.99, 1, 1)], [(1, "pr_bundle", "pull_request", 0.1, 0.99, 1)])

    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_scores").fetchone()[0] == 2
    assert processed_conn.execute("SELECT r_score FROM event_r_scores WHERE event_id=2").fetchone()[0] == 0.7
