import pytest

from src.api import repositories
from tests.api.conftest import seed_repo


def test_list_repositories_empty(data_dir):
    assert repositories.list_repositories() == []


def test_list_repositories_returns_seeded_repo(data_dir):
    seed_repo(data_dir, "o__r")

    repos = repositories.list_repositories()

    assert len(repos) == 1
    assert repos[0]["safe_name"] == "o__r"
    assert repos[0]["counts"]["commits"] == 1
    assert repos[0]["counts"]["pull_requests"] == 1
    assert repos[0]["contributor_count"] == 1
    assert repos[0]["event_counts"] == {"pr_bundle": 1}


def test_get_repository_not_found_raises(data_dir):
    with pytest.raises(repositories.RepositoryNotFound):
        repositories.get_repository("does_not_exist")


def test_get_repository_without_processed_data(data_dir):
    seed_repo(data_dir, "o__r", with_processed=False)

    repo = repositories.get_repository("o__r")

    assert repo["contributor_count"] is None
    assert repo["event_counts"] == {}


def test_list_events_filters_by_granularity_and_type(data_dir):
    seed_repo(data_dir, "o__r")

    result = repositories.list_events("o__r", granularity="pr_bundle", event_type=None, limit=50, offset=0)
    assert result["total"] == 1
    assert result["events"][0]["title"] == "Add feature"
    assert result["events"][0]["author"] == {"name": "Bob", "github_login": "bob", "is_bot": False}

    empty = repositories.list_events("o__r", granularity="commit_level", event_type=None, limit=50, offset=0)
    assert empty["total"] == 0

    filtered_out = repositories.list_events("o__r", granularity="pr_bundle", event_type="standalone_commit", limit=50, offset=0)
    assert filtered_out["total"] == 0


def test_list_events_without_processed_data_raises(data_dir):
    seed_repo(data_dir, "o__r", with_processed=False)

    with pytest.raises(repositories.RepositoryNotFound):
        repositories.list_events("o__r", granularity="pr_bundle", event_type=None, limit=50, offset=0)


def test_list_events_includes_empty_thresholds_when_not_scored(data_dir):
    seed_repo(data_dir, "o__r")

    result = repositories.list_events("o__r", granularity="pr_bundle", event_type=None, limit=50, offset=0)

    assert result["p_thresholds"] == {}
    assert result["r_thresholds"] == {}


def test_list_events_filters_by_high_p_and_includes_thresholds(data_dir):
    from src.processing.schema import connect as connect_processed
    from src.scoring.schema import create_schema as create_scoring_schema

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_scoring_schema(processed_conn)
    processed_conn.execute(
        "INSERT INTO event_p_scores (event_id, repo_id, granularity, event_type, p_score, features_used, is_high_p) "
        "VALUES (?, 1, 'pr_bundle', 'pull_request', 0.9, 5, 1)",
        (event_id,),
    )
    processed_conn.execute(
        "INSERT INTO p_score_thresholds (repo_id, granularity, event_type, top_percentile, threshold_score, group_size) "
        "VALUES (1, 'pr_bundle', 'pull_request', 0.1, 0.85, 1)"
    )
    processed_conn.commit()

    high = repositories.list_events("o__r", "pr_bundle", None, 50, 0, high_p=True)
    assert high["total"] == 1
    assert high["p_thresholds"] == {"pull_request": {"threshold_score": 0.85, "group_size": 1, "top_percentile": 0.1}}

    low = repositories.list_events("o__r", "pr_bundle", None, 50, 0, high_p=False)
    assert low["total"] == 0


def test_list_events_filters_by_high_r_and_includes_thresholds(data_dir):
    from src.features.schema import create_r_schema as create_r_features_schema
    from src.processing.schema import connect as connect_processed
    from src.scoring.schema import create_r_schema as create_r_scoring_schema

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_r_features_schema(processed_conn)
    create_r_scoring_schema(processed_conn)
    processed_conn.execute(
        "INSERT INTO event_r_scores (event_id, repo_id, granularity, event_type, r_score, features_used, is_high_r) "
        "VALUES (?, 1, 'pr_bundle', 'pull_request', 0.9, 3, 1)",
        (event_id,),
    )
    processed_conn.execute(
        "INSERT INTO r_score_thresholds (repo_id, granularity, event_type, top_percentile, threshold_score, group_size) "
        "VALUES (1, 'pr_bundle', 'pull_request', 0.1, 0.85, 1)"
    )
    processed_conn.commit()

    high = repositories.list_events("o__r", "pr_bundle", None, 50, 0, high_r=True)
    assert high["total"] == 1
    assert high["r_thresholds"] == {"pull_request": {"threshold_score": 0.85, "group_size": 1, "top_percentile": 0.1}}
    assert high["events"][0]["r_score"] == {"r_score": 0.9, "features_used": 3, "is_high_r": True}

    low = repositories.list_events("o__r", "pr_bundle", None, 50, 0, high_r=False)
    assert low["total"] == 0


def test_list_events_high_p_filter_returns_empty_when_p_scores_not_computed(data_dir):
    # Regression test: pallets/markupsafe hit a 500 in production because
    # high_p was requested while event_p_scores didn't exist yet for that
    # repo (P scoring never ran there, only R had) -- the JOIN raised
    # sqlite3.OperationalError instead of degrading to "zero matches,"
    # unlike every other "not computed yet" path in this module.
    seed_repo(data_dir, "o__r")

    result = repositories.list_events("o__r", "pr_bundle", None, 50, 0, high_p=True)

    assert result["total"] == 0
    assert result["events"] == []
    assert result["p_thresholds"] == {}


def test_list_events_high_r_filter_returns_empty_when_r_scores_not_computed(data_dir):
    seed_repo(data_dir, "o__r")

    result = repositories.list_events("o__r", "pr_bundle", None, 50, 0, high_r=True)

    assert result["total"] == 0
    assert result["events"] == []
    assert result["r_thresholds"] == {}


def test_list_events_combined_high_p_and_high_r_filters_when_only_r_computed(data_dir):
    # Reproduces the exact failing request: both filters set, but only one
    # axis's score table exists for this repo.
    from src.features.schema import create_r_schema as create_r_features_schema
    from src.processing.schema import connect as connect_processed
    from src.scoring.schema import create_r_schema as create_r_scoring_schema

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_r_features_schema(processed_conn)
    create_r_scoring_schema(processed_conn)
    processed_conn.execute(
        "INSERT INTO event_r_scores (event_id, repo_id, granularity, event_type, r_score, features_used, is_high_r) "
        "VALUES (?, 1, 'pr_bundle', 'pull_request', 0.9, 3, 1)",
        (event_id,),
    )
    processed_conn.commit()

    result = repositories.list_events("o__r", "pr_bundle", None, 50, 0, high_p=True, high_r=True)

    assert result["total"] == 0
    assert result["events"] == []


def test_get_event_includes_commits_and_pr_detail(data_dir):
    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    event = repositories.get_event("o__r", event_id)

    assert event["title"] == "Add feature"
    assert event["pr_detail"]["state"] == "closed"
    assert event["pr_detail"]["body"] == "desc"
    assert len(event["commits"]) == 1
    assert event["commits"][0]["hash"] == "c1"
    assert event["commits"][0]["author_name"] == "Alice"


def test_get_event_not_found_raises(data_dir):
    seed_repo(data_dir, "o__r")
    with pytest.raises(repositories.RepositoryNotFound):
        repositories.get_event("o__r", 9999)


def test_get_event_p_features_none_when_not_yet_extracted(data_dir):
    """Stage 2's P feature extraction hasn't run for this repo — None, not
    an empty dict, distinguishes "not computed" from "computed as empty"."""
    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    event = repositories.get_event("o__r", event_id)

    assert event["p_features"] is None


def test_get_event_includes_p_features_when_extracted(data_dir):
    from src.features.schema import create_schema as create_features_schema
    from src.processing.schema import connect as connect_processed

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_features_schema(processed_conn)
    processed_conn.execute(
        """
        INSERT INTO event_p_features (
            event_id, repo_id, comment_count, comment_count_status,
            distinct_commenters, distinct_commenters_status,
            reviewer_count, reviewer_count_status, review_rounds, review_rounds_status,
            files_changed, files_changed_status, churn, churn_status,
            issue_link_present, issue_link_present_status, issue_has_label, issue_has_label_status,
            release_proximity, release_proximity_status, reaction_count, reaction_count_status
        ) VALUES (?, 1, 5, 'complete', 2, 'complete', 1, 'complete', 1, 'complete',
                  3, 'complete', 42, 'complete', 1, 'complete', NULL, 'not_applicable',
                  86400, 'complete', 0, 'complete')
        """,
        (event_id,),
    )
    processed_conn.commit()

    event = repositories.get_event("o__r", event_id)

    assert event["p_features"]["comment_count"] == {"value": 5, "status": "complete"}
    assert event["p_features"]["issue_link_present"] == {"value": True, "status": "complete"}
    assert event["p_features"]["issue_has_label"] == {"value": None, "status": "not_applicable"}
    assert event["p_features"]["release_proximity"] == {"value": 86400, "status": "complete"}


def test_get_event_p_score_none_when_not_yet_computed(data_dir):
    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    event = repositories.get_event("o__r", event_id)

    assert event["p_score"] is None


def test_get_event_and_list_events_include_p_score_when_computed(data_dir):
    from src.processing.schema import connect as connect_processed
    from src.scoring.schema import create_schema as create_scoring_schema

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_scoring_schema(processed_conn)
    processed_conn.execute(
        "INSERT INTO event_p_scores (event_id, repo_id, granularity, event_type, p_score, features_used, is_high_p) "
        "VALUES (?, 1, 'pr_bundle', 'pull_request', 0.87, 9, 1)",
        (event_id,),
    )
    processed_conn.commit()

    event = repositories.get_event("o__r", event_id)
    assert event["p_score"] == {"p_score": 0.87, "features_used": 9, "is_high_p": True}

    listed = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]
    assert listed["p_score"] == {"p_score": 0.87, "features_used": 9, "is_high_p": True}


def test_get_event_r_features_none_when_not_yet_extracted(data_dir):
    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    event = repositories.get_event("o__r", event_id)

    assert event["r_features"] is None


def test_get_event_includes_r_features_when_extracted(data_dir):
    from src.features.schema import create_r_schema
    from src.processing.schema import connect as connect_processed

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_r_schema(processed_conn)
    processed_conn.execute(
        """
        INSERT INTO event_r_features (
            event_id, repo_id, maturity, maturity_status,
            files_survived, files_survived_status,
            subsequent_modification_count, subsequent_modification_count_status,
            releases_since_count, releases_since_count_status,
            later_references_count, later_references_count_status
        ) VALUES (?, 1, 0.87, 'complete', 6, 'complete', 140, 'complete', NULL, 'not_applicable', 3, 'complete')
        """,
        (event_id,),
    )
    processed_conn.commit()

    event = repositories.get_event("o__r", event_id)

    assert event["r_features"]["maturity"] == {"value": 0.87, "status": "complete"}
    assert event["r_features"]["features"]["files_survived"] == {"value": 6, "status": "complete"}
    assert event["r_features"]["features"]["subsequent_modification_count"] == {"value": 140, "status": "complete"}
    assert event["r_features"]["features"]["releases_since_count"] == {"value": None, "status": "not_applicable"}
    assert event["r_features"]["features"]["later_references_count"] == {"value": 3, "status": "complete"}


def test_get_event_r_score_none_when_not_yet_computed(data_dir):
    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    event = repositories.get_event("o__r", event_id)

    assert event["r_score"] is None


def test_get_event_and_list_events_include_r_score_when_computed(data_dir):
    from src.processing.schema import connect as connect_processed
    from src.scoring.schema import create_r_schema as create_r_scoring_schema

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_r_scoring_schema(processed_conn)
    processed_conn.execute(
        "INSERT INTO event_r_scores (event_id, repo_id, granularity, event_type, r_score, features_used, is_high_r) "
        "VALUES (?, 1, 'pr_bundle', 'pull_request', 0.72, 3, 0)",
        (event_id,),
    )
    processed_conn.commit()

    event = repositories.get_event("o__r", event_id)
    assert event["r_score"] == {"r_score": 0.72, "features_used": 3, "is_high_r": False}

    listed = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]
    assert listed["r_score"] == {"r_score": 0.72, "features_used": 3, "is_high_r": False}
