from src.divergence.classify import classify_divergence


def _insert_event(conn, event_id, repo_id=1, granularity="pr_bundle", event_type="pull_request"):
    conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, ?, ?, NULL, NULL, 't', '2024-01-01')",
        (event_id, repo_id, granularity, event_type),
    )


def _insert_p_score(conn, event_id, repo_id=1, granularity="pr_bundle", event_type="pull_request", p_score=0.5, is_high_p=1, features_used=5):
    conn.execute(
        "INSERT INTO event_p_scores (event_id, repo_id, granularity, event_type, p_score, features_used, is_high_p) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (event_id, repo_id, granularity, event_type, p_score, features_used, is_high_p),
    )


def _insert_r_score(conn, event_id, repo_id=1, granularity="pr_bundle", event_type="pull_request", r_score=0.5, is_high_r=1, features_used=3):
    conn.execute(
        "INSERT INTO event_r_scores (event_id, repo_id, granularity, event_type, r_score, features_used, is_high_r) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (event_id, repo_id, granularity, event_type, r_score, features_used, is_high_r),
    )


def test_all_four_quadrants_classified_correctly(processed_conn):
    # event 1: High P, High R -> Truly Important
    _insert_event(processed_conn, 1)
    _insert_p_score(processed_conn, 1, is_high_p=1)
    _insert_r_score(processed_conn, 1, is_high_r=1)
    # event 2: High P, Low R -> Discussed but Forgotten
    _insert_event(processed_conn, 2)
    _insert_p_score(processed_conn, 2, is_high_p=1)
    _insert_r_score(processed_conn, 2, is_high_r=0)
    # event 3: Low P, High R -> Silent but Critical
    _insert_event(processed_conn, 3)
    _insert_p_score(processed_conn, 3, is_high_p=0)
    _insert_r_score(processed_conn, 3, is_high_r=1)
    # event 4: Low P, Low R -> Routine Noise
    _insert_event(processed_conn, 4)
    _insert_p_score(processed_conn, 4, is_high_p=0)
    _insert_r_score(processed_conn, 4, is_high_r=0)
    processed_conn.commit()

    result = classify_divergence(processed_conn, repo_id=1)
    quadrants = {r["event_id"]: r["quadrant"] for r in result["rows"]}

    assert quadrants[1] == "truly_important"
    assert quadrants[2] == "discussed_but_forgotten"
    assert quadrants[3] == "silent_but_critical"
    assert quadrants[4] == "routine_noise"
    assert result["summary"]["quadrant_counts"] == {
        "truly_important": 1, "discussed_but_forgotten": 1,
        "silent_but_critical": 1, "routine_noise": 1,
    }
    assert result["summary"]["events_classified"] == 4


def test_event_missing_r_score_is_excluded_not_treated_as_low(processed_conn):
    # event has a P score but no R score row at all (R Phase 3 hasn't run
    # for it) -- must not be silently treated as "Low R".
    _insert_event(processed_conn, 1)
    _insert_p_score(processed_conn, 1, is_high_p=1)
    processed_conn.commit()

    result = classify_divergence(processed_conn, repo_id=1)

    assert result["rows"] == []
    assert result["summary"]["events_classified"] == 0
    assert result["summary"]["events_with_p_score"] == 1
    assert result["summary"]["events_with_r_score"] == 0


def test_event_with_null_is_high_r_is_excluded(processed_conn):
    # r_score row exists but is_high_r is NULL -- e.g. the event was too
    # young (MIN_MATURITY_FOR_SCORING) or had zero applicable R features.
    # Still not the same as "Low R".
    _insert_event(processed_conn, 1)
    _insert_p_score(processed_conn, 1, is_high_p=1)
    _insert_r_score(processed_conn, 1, r_score=None, is_high_r=None, features_used=0)
    processed_conn.commit()

    result = classify_divergence(processed_conn, repo_id=1)

    assert result["rows"] == []
    assert result["summary"]["events_classified"] == 0
    assert result["summary"]["events_with_r_score"] == 0


def test_classification_scoped_by_repo_id(processed_conn):
    _insert_event(processed_conn, 1, repo_id=1)
    _insert_p_score(processed_conn, 1, repo_id=1, is_high_p=1)
    _insert_r_score(processed_conn, 1, repo_id=1, is_high_r=1)

    _insert_event(processed_conn, 2, repo_id=2)
    _insert_p_score(processed_conn, 2, repo_id=2, is_high_p=0)
    _insert_r_score(processed_conn, 2, repo_id=2, is_high_r=0)
    processed_conn.commit()

    result = classify_divergence(processed_conn, repo_id=1)

    assert len(result["rows"]) == 1
    assert result["rows"][0]["event_id"] == 1


def test_p_score_and_r_score_values_carried_through_for_provenance(processed_conn):
    _insert_event(processed_conn, 1)
    _insert_p_score(processed_conn, 1, p_score=0.87, is_high_p=1)
    _insert_r_score(processed_conn, 1, r_score=0.42, is_high_r=0)
    processed_conn.commit()

    result = classify_divergence(processed_conn, repo_id=1)
    row = result["rows"][0]

    assert row["p_score"] == 0.87
    assert row["r_score"] == 0.42
    assert row["granularity"] == "pr_bundle"
    assert row["event_type"] == "pull_request"
