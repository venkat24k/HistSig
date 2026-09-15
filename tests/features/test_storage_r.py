from src.features.storage import insert_r_features


def _insert_event(conn, event_id, repo_id=1):
    conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, 'commit_level', 'commit', NULL, 'abc', 't', '2024-01-01')",
        (event_id, repo_id),
    )
    conn.commit()


def _row(
    event_id,
    maturity=0.5,
    maturity_status="complete",
    files_survived=3,
    files_survived_status="complete",
    subsequent_modification_count=2,
    subsequent_modification_count_status="complete",
    releases_since_count=1,
    releases_since_count_status="complete",
    later_references_count=0,
    later_references_count_status="complete",
):
    return {
        "event_id": event_id,
        "maturity": maturity,
        "maturity_status": maturity_status,
        "files_survived": files_survived,
        "files_survived_status": files_survived_status,
        "subsequent_modification_count": subsequent_modification_count,
        "subsequent_modification_count_status": subsequent_modification_count_status,
        "releases_since_count": releases_since_count,
        "releases_since_count_status": releases_since_count_status,
        "later_references_count": later_references_count,
        "later_references_count_status": later_references_count_status,
    }


def test_insert_r_features_is_idempotent(processed_conn):
    _insert_event(processed_conn, 1)
    rows = [_row(1)]
    insert_r_features(processed_conn, repo_id=1, rows=rows)
    insert_r_features(processed_conn, repo_id=1, rows=rows)

    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_features").fetchone()[0] == 1
    row = processed_conn.execute("SELECT maturity, files_survived FROM event_r_features WHERE event_id=1").fetchone()
    assert row == (0.5, 3)


def test_insert_r_features_stores_null_for_not_applicable(processed_conn):
    _insert_event(processed_conn, 1)
    rows = [_row(1, maturity=None, maturity_status="not_applicable")]
    insert_r_features(processed_conn, repo_id=1, rows=rows)

    row = processed_conn.execute("SELECT maturity, maturity_status FROM event_r_features WHERE event_id=1").fetchone()
    assert row == (None, "not_applicable")


def test_insert_r_features_does_not_clobber_other_repo(processed_conn):
    _insert_event(processed_conn, 1, repo_id=1)
    _insert_event(processed_conn, 2, repo_id=2)
    insert_r_features(processed_conn, repo_id=1, rows=[_row(1, maturity=0.1)])
    insert_r_features(processed_conn, repo_id=2, rows=[_row(2, maturity=0.9)])

    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_features").fetchone()[0] == 2

    insert_r_features(processed_conn, repo_id=1, rows=[_row(1, maturity=0.99)])
    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_features").fetchone()[0] == 2
    assert processed_conn.execute("SELECT maturity FROM event_r_features WHERE event_id=2").fetchone()[0] == 0.9
