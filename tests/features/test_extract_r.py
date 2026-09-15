from src.features.extract import extract_r_features


def _set_availability(conn, repo_id, earliest, latest):
    conn.execute(
        "INSERT INTO repository_data_availability (repo_id, has_releases, has_pr_reviews, has_issues, earliest_commit_date, latest_commit_date, normalized_at) "
        "VALUES (?, 0, 0, 0, ?, ?, ?)",
        (repo_id, earliest, latest, latest),
    )


def test_extract_r_features_end_to_end(raw_conn, processed_conn):
    raw_conn.execute("INSERT INTO releases (repo_id, tag_name, published_at) VALUES (1, 'v1.0', '2020-01-05T00:00:00Z')")
    raw_conn.commit()

    _set_availability(processed_conn, 1, "2020-01-01T00:00:00Z", "2020-01-11T00:00:00Z")

    processed_conn.execute(
        "INSERT INTO candidate_events (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (1, 'commit_level', 'commit', NULL, 'c1', 't', '2020-01-01T00:00:00Z')"
    )
    event_id = processed_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    processed_conn.execute("INSERT INTO event_commits (event_id, commit_hash) VALUES (?, 'c1')", (event_id,))
    processed_conn.execute(
        "INSERT INTO commit_annotations (repo_id, commit_hash, contributor_id, is_revert) VALUES (1, 'c1', NULL, 0)"
    )
    processed_conn.execute(
        "INSERT INTO file_identities (repo_id, first_path, last_path, is_deleted) VALUES (1, 'a.py', 'a.py', 0)"
    )
    file_id = processed_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    processed_conn.execute(
        "INSERT INTO file_path_history (repo_id, commit_hash, path, change_type, file_id) VALUES (1, 'c1', 'a.py', 'ADD', ?)",
        (file_id,),
    )
    processed_conn.commit()

    summary = extract_r_features(raw_conn, processed_conn, repo_id=1)

    assert summary["events_processed"] == 1
    assert summary["maturity_by_status"] == {"complete": 1}
    assert summary["files_survived_by_status"] == {"complete": 1}
    assert summary["subsequent_modification_count_by_status"] == {"complete": 1}
    assert summary["releases_since_count_by_status"] == {"complete": 1}
    assert summary["later_references_count_by_status"] == {"not_applicable": 1}  # standalone commit, not a PR

    row = processed_conn.execute(
        "SELECT maturity, files_survived, subsequent_modification_count, releases_since_count, later_references_count "
        "FROM event_r_features WHERE event_id=?",
        (event_id,),
    ).fetchone()
    assert row[0] == 1.0  # event occurred exactly at earliest_commit_date
    assert row[1] == 1
    assert row[2] == 0  # no other commit touches a.py
    assert row[3] == 1  # v1.0 published after this event
    assert row[4] is None  # not a pull_request event


def test_extract_r_features_not_applicable_when_availability_missing(raw_conn, processed_conn):
    processed_conn.execute(
        "INSERT INTO candidate_events (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (1, 'commit_level', 'commit', NULL, 'c1', 't', '2020-01-01T00:00:00Z')"
    )
    processed_conn.commit()

    summary = extract_r_features(raw_conn, processed_conn, repo_id=1)

    assert summary["maturity_by_status"] == {"not_applicable": 1}
    assert summary["files_survived_by_status"] == {"not_applicable": 1}
    assert summary["subsequent_modification_count_by_status"] == {"not_applicable": 1}
    assert summary["releases_since_count_by_status"] == {"not_applicable": 1}  # repo has no releases
    assert summary["later_references_count_by_status"] == {"not_applicable": 1}  # standalone commit, not a PR


def test_extract_r_features_computes_later_references_for_pull_request_events(raw_conn, processed_conn):
    raw_conn.execute(
        "INSERT INTO pull_requests (repo_id, number, title, state, cross_references_truncated) "
        "VALUES (1, 7, 't', 'merged', 0)"
    )
    pr_id = raw_conn.execute("SELECT id FROM pull_requests WHERE repo_id=1 AND number=7").fetchone()[0]
    raw_conn.execute(
        "INSERT INTO pr_cross_references (pr_id, source_number, referenced_at) VALUES (?, 8, '2020-02-01T00:00:00Z')",
        (pr_id,),
    )
    raw_conn.commit()

    _set_availability(processed_conn, 1, "2020-01-01T00:00:00Z", "2020-02-11T00:00:00Z")
    processed_conn.execute(
        "INSERT INTO candidate_events (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (1, 'pr_bundle', 'pull_request', 7, NULL, 't', '2020-01-15T00:00:00Z')"
    )
    processed_conn.commit()

    summary = extract_r_features(raw_conn, processed_conn, repo_id=1)

    assert summary["later_references_count_by_status"] == {"complete": 1}
    value = processed_conn.execute("SELECT later_references_count FROM event_r_features").fetchone()[0]
    assert value == 1


def test_extract_r_features_is_idempotent(raw_conn, processed_conn):
    _set_availability(processed_conn, 1, "2020-01-01T00:00:00Z", "2020-01-11T00:00:00Z")
    processed_conn.execute(
        "INSERT INTO candidate_events (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (1, 'commit_level', 'commit', NULL, 'c1', 't', '2020-01-01T00:00:00Z')"
    )
    processed_conn.commit()

    extract_r_features(raw_conn, processed_conn, repo_id=1)
    extract_r_features(raw_conn, processed_conn, repo_id=1)

    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_features").fetchone()[0] == 1
