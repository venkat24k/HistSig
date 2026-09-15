import pytest

from src.scoring.p_score import _P_FEATURE_NAMES, _percentile_ranks, compute_p_scores


def _insert_event(conn, event_id, repo_id=1, granularity="pr_bundle", event_type="pull_request"):
    conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, ?, ?, NULL, NULL, 't', '2024-01-01')",
        (event_id, repo_id, granularity, event_type),
    )


def _insert_features(conn, event_id, repo_id=1, **overrides):
    """overrides: feature_name=(value, status). Every feature not passed
    defaults to (None, 'not_applicable')."""
    values = {name: (None, "not_applicable") for name in _P_FEATURE_NAMES}
    values.update(overrides)
    columns = ["event_id", "repo_id"]
    params = [event_id, repo_id]
    for name in _P_FEATURE_NAMES:
        value, status = values[name]
        columns += [name, f"{name}_status"]
        params += [value, status]
    conn.execute(
        f"INSERT INTO event_p_features ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        params,
    )
    conn.commit()


# --- _percentile_ranks ---

def test_percentile_ranks_hand_computed_with_ties():
    # sorted: 0, 5, 5, 10, 20 (n=5) -> avg ranks 1, 2.5, 2.5, 4, 5 -> (rank-0.5)/5
    values = [(1, 0), (2, 5), (3, 5), (4, 10), (5, 20)]

    ranks = _percentile_ranks(values)

    assert ranks[1] == pytest.approx(0.1)
    assert ranks[2] == pytest.approx(0.4)
    assert ranks[3] == pytest.approx(0.4)
    assert ranks[4] == pytest.approx(0.7)
    assert ranks[5] == pytest.approx(0.9)


def test_percentile_ranks_single_event_is_neutral():
    assert _percentile_ranks([(1, 42)]) == {1: 0.5}


def test_percentile_ranks_empty_is_empty():
    assert _percentile_ranks([]) == {}


# --- compute_p_scores ---

def test_compute_p_scores_matches_hand_computed_single_feature_example(processed_conn):
    values = [(1, 0), (2, 5), (3, 5), (4, 10), (5, 20)]
    for event_id, cc in values:
        _insert_event(processed_conn, event_id)
        _insert_features(processed_conn, event_id, comment_count=(cc, "complete"))
    processed_conn.commit()

    result = compute_p_scores(processed_conn, repo_id=1, top_percentile=0.10)
    scores = {r[0]: r[4] for r in result["score_rows"]}
    is_high = {r[0]: r[6] for r in result["score_rows"]}

    assert scores[1] == pytest.approx(0.1)
    assert scores[2] == pytest.approx(0.4)
    assert scores[3] == pytest.approx(0.4)
    assert scores[4] == pytest.approx(0.7)
    assert scores[5] == pytest.approx(0.9)

    # top-1-of-5 (round(5*0.10) -> min 1) is only the highest scorer
    assert is_high[5] == 1
    assert is_high[4] == 0
    assert is_high[1] == 0


def test_not_applicable_feature_excluded_from_average_not_treated_as_zero(processed_conn):
    # event 1: only comment_count applies (churn is not_applicable)
    # event 2: both comment_count and churn apply
    _insert_event(processed_conn, 1)
    _insert_features(processed_conn, 1, comment_count=(10, "complete"), churn=(None, "not_applicable"))
    _insert_event(processed_conn, 2)
    _insert_features(processed_conn, 2, comment_count=(0, "complete"), churn=(100, "complete"))
    processed_conn.commit()

    result = compute_p_scores(processed_conn, repo_id=1, top_percentile=0.5)
    rows = {r[0]: r for r in result["score_rows"]}

    # comment_count (n=2): event1=10 -> rank (2-0.5)/2=0.75; event2=0 -> (1-0.5)/2=0.25
    # churn (n=1, only event2 applicable): event2 -> neutral 0.5
    # event1's score is comment_count's rank ALONE (0.75) -- churn's absence must not drag it toward 0
    assert rows[1][4] == pytest.approx(0.75)
    assert rows[1][5] == 1  # features_used
    assert rows[2][4] == pytest.approx((0.25 + 0.5) / 2)
    assert rows[2][5] == 2


def test_event_with_zero_applicable_features_gets_null_score(processed_conn):
    _insert_event(processed_conn, 1)
    _insert_features(processed_conn, 1)  # every feature not_applicable
    processed_conn.commit()

    result = compute_p_scores(processed_conn, repo_id=1)
    row = result["score_rows"][0]

    assert row[4] is None  # p_score
    assert row[5] == 0  # features_used
    assert row[6] is None  # is_high_p


def test_event_types_scored_in_separate_groups(processed_conn):
    _insert_event(processed_conn, 1, event_type="pull_request")
    _insert_features(processed_conn, 1, comment_count=(0, "complete"))
    _insert_event(processed_conn, 2, event_type="pull_request")
    _insert_features(processed_conn, 2, comment_count=(10, "complete"))

    _insert_event(processed_conn, 3, event_type="standalone_commit")
    _insert_features(processed_conn, 3, files_changed=(1, "complete"))
    _insert_event(processed_conn, 4, event_type="standalone_commit")
    _insert_features(processed_conn, 4, files_changed=(2, "complete"))
    processed_conn.commit()

    result = compute_p_scores(processed_conn, repo_id=1, top_percentile=0.5)
    scores = {r[0]: r[4] for r in result["score_rows"]}

    assert scores[1] == pytest.approx(0.25)
    assert scores[2] == pytest.approx(0.75)
    assert scores[3] == pytest.approx(0.25)
    assert scores[4] == pytest.approx(0.75)

    groups = {(g["granularity"], g["event_type"]): g["group_size"] for g in result["summary"]["groups"]}
    assert groups[("pr_bundle", "pull_request")] == 2
    assert groups[("pr_bundle", "standalone_commit")] == 2


def test_granularities_scored_in_separate_groups(processed_conn):
    _insert_event(processed_conn, 1, granularity="pr_bundle", event_type="pull_request")
    _insert_features(processed_conn, 1, comment_count=(1, "complete"))
    _insert_event(processed_conn, 2, granularity="commit_level", event_type="commit")
    _insert_features(processed_conn, 2, files_changed=(1, "complete"))
    processed_conn.commit()

    result = compute_p_scores(processed_conn, repo_id=1, top_percentile=0.5)

    assert len(result["summary"]["groups"]) == 2


def test_invalid_top_percentile_raises(processed_conn):
    with pytest.raises(ValueError):
        compute_p_scores(processed_conn, repo_id=1, top_percentile=0)
    with pytest.raises(ValueError):
        compute_p_scores(processed_conn, repo_id=1, top_percentile=1.5)
