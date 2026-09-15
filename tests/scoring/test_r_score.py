import pytest

from src.scoring.r_score import _R_FEATURE_NAMES, compute_r_scores


def _insert_event(conn, event_id, repo_id=1, granularity="pr_bundle", event_type="pull_request"):
    conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, ?, ?, NULL, NULL, 't', '2024-01-01')",
        (event_id, repo_id, granularity, event_type),
    )


def _insert_r_features(conn, event_id, repo_id=1, maturity=(0.5, "complete"), **overrides):
    """overrides: feature_name=(value, status) for names in _R_FEATURE_NAMES.
    Every one not passed defaults to (None, 'not_applicable'). `maturity`
    is always stored (event_r_features requires it); its *value* must
    never affect the score average (tested below), but since events under
    MIN_MATURITY_FOR_SCORING it's used to exclude events from ranking
    entirely (tested further below) — the default of 0.5 here is safely
    above that cutoff so existing tests aren't affected by it."""
    values = {name: (None, "not_applicable") for name in _R_FEATURE_NAMES}
    values.update(overrides)
    columns = ["event_id", "repo_id", "maturity", "maturity_status"]
    params = [event_id, repo_id, maturity[0], maturity[1]]
    for name in _R_FEATURE_NAMES:
        value, status = values[name]
        columns += [name, f"{name}_status"]
        params += [value, status]
    conn.execute(
        f"INSERT INTO event_r_features ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        params,
    )
    conn.commit()


def test_compute_r_scores_matches_hand_computed_single_feature_example(processed_conn):
    values = [(1, 0), (2, 5), (3, 5), (4, 10), (5, 20)]
    for event_id, count in values:
        _insert_event(processed_conn, event_id)
        _insert_r_features(processed_conn, event_id, files_survived=(count, "complete"))
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, top_percentile=0.10)
    scores = {r[0]: r[4] for r in result["score_rows"]}
    is_high = {r[0]: r[6] for r in result["score_rows"]}

    assert scores[1] == pytest.approx(0.1)
    assert scores[2] == pytest.approx(0.4)
    assert scores[3] == pytest.approx(0.4)
    assert scores[4] == pytest.approx(0.7)
    assert scores[5] == pytest.approx(0.9)
    assert is_high[5] == 1
    assert is_high[4] == 0


def test_maturity_never_affects_the_score_even_though_it_varies(processed_conn):
    # Two events with IDENTICAL files_survived/subsequent_modification_count/
    # releases_since_count but different maturity -- their scores must come
    # out identical, proving maturity plays no part in the average. Both
    # stay above the default min_maturity cutoff (0.05) so this isolates
    # "maturity doesn't affect the score average" from the separate
    # "too-young events are excluded from ranking" behavior tested below.
    _insert_event(processed_conn, 1)
    _insert_r_features(
        processed_conn, 1, maturity=(0.10, "complete"),
        files_survived=(3, "complete"), subsequent_modification_count=(7, "complete"), releases_since_count=(2, "complete"),
    )
    _insert_event(processed_conn, 2)
    _insert_r_features(
        processed_conn, 2, maturity=(0.99, "complete"),
        files_survived=(3, "complete"), subsequent_modification_count=(7, "complete"), releases_since_count=(2, "complete"),
    )
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, top_percentile=0.5)
    scores = {r[0]: r[4] for r in result["score_rows"]}

    assert scores[1] == pytest.approx(scores[2])


def test_not_applicable_feature_excluded_from_average_not_treated_as_zero(processed_conn):
    _insert_event(processed_conn, 1)
    _insert_r_features(processed_conn, 1, files_survived=(10, "complete"), releases_since_count=(None, "not_applicable"))
    _insert_event(processed_conn, 2)
    _insert_r_features(processed_conn, 2, files_survived=(0, "complete"), releases_since_count=(100, "complete"))
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, top_percentile=0.5)
    rows = {r[0]: r for r in result["score_rows"]}

    assert rows[1][4] == pytest.approx(0.75)  # files_survived rank alone, not dragged toward 0
    assert rows[1][5] == 1
    assert rows[2][4] == pytest.approx((0.25 + 0.5) / 2)
    assert rows[2][5] == 2


def test_event_with_zero_applicable_features_gets_null_score(processed_conn):
    _insert_event(processed_conn, 1)
    _insert_r_features(processed_conn, 1)  # every real feature not_applicable
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1)
    row = result["score_rows"][0]

    assert row[4] is None
    assert row[5] == 0
    assert row[6] is None


def test_later_references_count_participates_in_the_average(processed_conn):
    # Same shape as the not_applicable-exclusion test above, but exercising
    # the 4th feature (later_references_count) specifically -- it must
    # participate in the average like any other R feature.
    _insert_event(processed_conn, 1)
    _insert_r_features(processed_conn, 1, files_survived=(10, "complete"), later_references_count=(None, "not_applicable"))
    _insert_event(processed_conn, 2)
    _insert_r_features(processed_conn, 2, files_survived=(0, "complete"), later_references_count=(100, "complete"))
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, top_percentile=0.5)
    rows = {r[0]: r for r in result["score_rows"]}

    assert rows[1][4] == pytest.approx(0.75)  # files_survived rank alone, not_applicable feature excluded
    assert rows[2][4] == pytest.approx((0.25 + 0.5) / 2)


def test_event_types_scored_in_separate_groups(processed_conn):
    _insert_event(processed_conn, 1, event_type="pull_request")
    _insert_r_features(processed_conn, 1, files_survived=(0, "complete"))
    _insert_event(processed_conn, 2, event_type="pull_request")
    _insert_r_features(processed_conn, 2, files_survived=(10, "complete"))

    _insert_event(processed_conn, 3, event_type="standalone_commit")
    _insert_r_features(processed_conn, 3, files_survived=(1, "complete"))
    _insert_event(processed_conn, 4, event_type="standalone_commit")
    _insert_r_features(processed_conn, 4, files_survived=(2, "complete"))
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, top_percentile=0.5)
    scores = {r[0]: r[4] for r in result["score_rows"]}

    assert scores[1] == pytest.approx(0.25)
    assert scores[2] == pytest.approx(0.75)
    assert scores[3] == pytest.approx(0.25)
    assert scores[4] == pytest.approx(0.75)


def test_invalid_top_percentile_raises(processed_conn):
    with pytest.raises(ValueError):
        compute_r_scores(processed_conn, repo_id=1, top_percentile=0)
    with pytest.raises(ValueError):
        compute_r_scores(processed_conn, repo_id=1, top_percentile=1.5)


# --- min_maturity exclusion ---

def test_too_young_event_is_excluded_from_ranking_even_with_a_dominant_feature_value(processed_conn):
    # event 1 is young (maturity 0.01, below the 0.05 default) but has a
    # huge files_survived value that would trivially top the ranking if
    # it were included -- it must come back unscored instead.
    _insert_event(processed_conn, 1)
    _insert_r_features(processed_conn, 1, maturity=(0.01, "complete"), files_survived=(1000, "complete"))
    _insert_event(processed_conn, 2)
    _insert_r_features(processed_conn, 2, maturity=(0.5, "complete"), files_survived=(5, "complete"))
    _insert_event(processed_conn, 3)
    _insert_r_features(processed_conn, 3, maturity=(0.5, "complete"), files_survived=(1, "complete"))
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, top_percentile=0.5, min_maturity=0.05)
    rows = {r[0]: r for r in result["score_rows"]}

    assert rows[1][4] is None  # r_score
    assert rows[1][6] is None  # is_high_r
    assert rows[1][5] == 1  # features_used still reported (informational)

    # excluding event 1 must not distort 2/3's ranks: with only two eligible
    # events, event2 (higher files_survived) gets rank 0.75, event3 gets 0.25.
    assert rows[2][4] == pytest.approx(0.75)
    assert rows[3][4] == pytest.approx(0.25)
    assert rows[2][6] == 1  # top 50% of the *eligible* pool of 2
    assert rows[3][6] == 0


def test_unknown_maturity_event_is_also_excluded(processed_conn):
    _insert_event(processed_conn, 1)
    _insert_r_features(processed_conn, 1, maturity=(None, "not_applicable"), files_survived=(100, "complete"))
    _insert_event(processed_conn, 2)
    _insert_r_features(processed_conn, 2, maturity=(0.5, "complete"), files_survived=(5, "complete"))
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, top_percentile=0.5, min_maturity=0.05)
    rows = {r[0]: r for r in result["score_rows"]}

    assert rows[1][4] is None
    assert rows[2][4] == pytest.approx(0.5)  # sole eligible event -> neutral rank


def test_group_size_in_threshold_reflects_only_eligible_events(processed_conn):
    _insert_event(processed_conn, 1)
    _insert_r_features(processed_conn, 1, maturity=(0.01, "complete"), files_survived=(1, "complete"))
    _insert_event(processed_conn, 2)
    _insert_r_features(processed_conn, 2, maturity=(0.5, "complete"), files_survived=(1, "complete"))
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, min_maturity=0.05)

    groups = {(g["granularity"], g["event_type"]): g["group_size"] for g in result["summary"]["groups"]}
    assert groups[("pr_bundle", "pull_request")] == 1  # only event 2
    assert result["summary"]["events_excluded_from_ranking"] == 1


def test_min_maturity_zero_disables_exclusion(processed_conn):
    _insert_event(processed_conn, 1)
    _insert_r_features(processed_conn, 1, maturity=(0.0, "complete"), files_survived=(1, "complete"))
    processed_conn.commit()

    result = compute_r_scores(processed_conn, repo_id=1, min_maturity=0.0)
    row = result["score_rows"][0]

    assert row[4] is not None  # event is scored, not excluded
