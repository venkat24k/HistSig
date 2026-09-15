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


def test_list_events_filters_by_quadrant(data_dir):
    from src.divergence.schema import create_schema as create_divergence_schema
    from src.processing.schema import connect as connect_processed

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_divergence_schema(processed_conn)
    processed_conn.execute(
        "INSERT INTO event_divergence (event_id, repo_id, granularity, event_type, p_score, r_score, is_high_p, is_high_r, quadrant) "
        "VALUES (?, 1, 'pr_bundle', 'pull_request', 0.9, 0.8, 1, 1, 'truly_important')",
        (event_id,),
    )
    processed_conn.commit()

    matching = repositories.list_events("o__r", "pr_bundle", None, 50, 0, quadrant="truly_important")
    assert matching["total"] == 1
    assert matching["events"][0]["divergence"] == {"quadrant": "truly_important", "p_score": 0.9, "r_score": 0.8}

    other = repositories.list_events("o__r", "pr_bundle", None, 50, 0, quadrant="routine_noise")
    assert other["total"] == 0


def test_list_events_quadrant_filter_returns_empty_when_divergence_not_computed(data_dir):
    seed_repo(data_dir, "o__r")

    result = repositories.list_events("o__r", "pr_bundle", None, 50, 0, quadrant="truly_important")

    assert result["total"] == 0
    assert result["events"] == []


def test_list_events_divergence_is_none_when_not_classified(data_dir):
    seed_repo(data_dir, "o__r")

    result = repositories.list_events("o__r", "pr_bundle", None, 50, 0)

    assert result["events"][0]["divergence"] is None


def test_get_divergence_summary_counts_all_four_quadrants(data_dir):
    from src.divergence.schema import create_schema as create_divergence_schema
    from src.processing.schema import connect as connect_processed

    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_divergence_schema(processed_conn)
    processed_conn.execute(
        "INSERT INTO event_divergence (event_id, repo_id, granularity, event_type, p_score, r_score, is_high_p, is_high_r, quadrant) "
        "VALUES (?, 1, 'pr_bundle', 'pull_request', 0.9, 0.8, 1, 1, 'truly_important')",
        (event_id,),
    )
    processed_conn.commit()

    summary = repositories.get_divergence_summary("o__r", "pr_bundle")

    assert summary == {
        "granularity": "pr_bundle",
        "counts": {
            "truly_important": 1, "discussed_but_forgotten": 0,
            "silent_but_critical": 0, "routine_noise": 0,
        },
    }


def test_get_divergence_summary_all_zero_when_not_computed(data_dir):
    seed_repo(data_dir, "o__r")

    summary = repositories.get_divergence_summary("o__r", "pr_bundle")

    assert summary["counts"] == {
        "truly_important": 0, "discussed_but_forgotten": 0,
        "silent_but_critical": 0, "routine_noise": 0,
    }


def _insert_scored_event(processed_conn, event_id, repo_id, p_score, r_score, granularity="pr_bundle"):
    processed_conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, ?, 'pull_request', NULL, NULL, 't', '2024-01-01')",
        (event_id, repo_id, granularity),
    )
    processed_conn.execute(
        "INSERT INTO event_p_scores (event_id, repo_id, granularity, event_type, p_score, features_used, is_high_p) "
        "VALUES (?, ?, ?, 'pull_request', ?, 1, 0)",
        (event_id, repo_id, granularity, p_score),
    )
    processed_conn.execute(
        "INSERT INTO event_r_scores (event_id, repo_id, granularity, event_type, r_score, features_used, is_high_r) "
        "VALUES (?, ?, ?, 'pull_request', ?, 1, 0)",
        (event_id, repo_id, granularity, r_score),
    )


def test_get_pr_heatmap_bins_events_by_p_and_r_score(data_dir):
    from src.processing.schema import connect as connect_processed
    from src.scoring.schema import create_r_schema as create_r_scoring_schema
    from src.scoring.schema import create_schema as create_p_scoring_schema

    seed_repo(data_dir, "o__r")
    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_p_scoring_schema(processed_conn)
    create_r_scoring_schema(processed_conn)
    # bins=10: 0.05 -> bin 0, 0.95 -> bin 9, and a second event landing in
    # the exact same cell to verify counts accumulate rather than overwrite.
    _insert_scored_event(processed_conn, 101, 1, p_score=0.05, r_score=0.95)
    _insert_scored_event(processed_conn, 102, 1, p_score=0.06, r_score=0.91)
    _insert_scored_event(processed_conn, 103, 1, p_score=1.0, r_score=1.0)  # exact 1.0 clamps into the last bin
    processed_conn.commit()

    result = repositories.get_pr_heatmap("o__r", "pr_bundle", bins=10)

    assert result["bins"] == 10
    assert result["total"] == 3
    cells_by_pos = {(c["p_bin"], c["r_bin"]): c["count"] for c in result["cells"]}
    assert len(result["cells"]) == 100  # full grid, including empty cells
    assert cells_by_pos[(0, 9)] == 2  # the two low-P/high-R events share a cell
    assert cells_by_pos[(9, 9)] == 1  # the (1.0, 1.0) event clamps into the last bin, not bin 10
    assert cells_by_pos[(5, 5)] == 0  # an empty cell is still present, at 0


def test_get_pr_heatmap_excludes_events_missing_either_score(data_dir):
    from src.processing.schema import connect as connect_processed
    from src.scoring.schema import create_r_schema as create_r_scoring_schema
    from src.scoring.schema import create_schema as create_p_scoring_schema

    seed_repo(data_dir, "o__r")
    processed_conn = connect_processed(str(data_dir / "processed" / "o__r.db"))
    create_p_scoring_schema(processed_conn)
    create_r_scoring_schema(processed_conn)
    _insert_scored_event(processed_conn, 101, 1, p_score=0.5, r_score=0.5)
    # An event with a P score but no R score row at all -- must not appear.
    processed_conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (102, 1, 'pr_bundle', 'pull_request', NULL, NULL, 't', '2024-01-01')"
    )
    processed_conn.execute(
        "INSERT INTO event_p_scores (event_id, repo_id, granularity, event_type, p_score, features_used, is_high_p) "
        "VALUES (102, 1, 'pr_bundle', 'pull_request', 0.9, 1, 1)"
    )
    processed_conn.commit()

    result = repositories.get_pr_heatmap("o__r", "pr_bundle")

    assert result["total"] == 1


def test_get_pr_heatmap_empty_when_not_scored(data_dir):
    seed_repo(data_dir, "o__r")

    result = repositories.get_pr_heatmap("o__r", "pr_bundle")

    assert result["total"] == 0
    assert all(c["count"] == 0 for c in result["cells"])
    assert len(result["cells"]) == 100


def test_get_commit_diff_returns_none_for_invalid_hash_format(data_dir):
    seed_repo(data_dir, "o__r")

    assert repositories.get_commit_diff("o__r", "not-a-hash!") is None
    assert repositories.get_commit_diff("o__r", "") is None
    assert repositories.get_commit_diff("o__r", "--upload-pack=x") is None


def test_get_commit_diff_returns_none_for_unknown_commit(data_dir):
    seed_repo(data_dir, "o__r")

    assert repositories.get_commit_diff("o__r", "0000000000000000000000000000000000000000") is None


def test_get_commit_diff_returns_real_diff_for_known_commit(data_dir):
    import sqlite3
    import subprocess

    seed_repo(data_dir, "o__r")

    clone_dir = data_dir / "raw" / "_clones" / "o__r"
    clone_dir.mkdir(parents=True)
    run = lambda *args: subprocess.run(["git", "-C", str(clone_dir), *args], check=True, capture_output=True)
    run("init", "-b", "main")
    run("config", "user.name", "Alice")
    run("config", "user.email", "alice@example.com")
    (clone_dir / "a.txt").write_text("hello\n")
    run("add", "a.txt")
    run("commit", "-m", "Initial commit")
    real_hash = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()

    # seed_repo's commits row uses hash 'c1' -- point it at the real
    # commit just created in the clone so the "known to this repo" check
    # and the actual git lookup agree.
    raw_conn = sqlite3.connect(str(data_dir / "raw" / "o__r.db"))
    raw_conn.execute("UPDATE commits SET hash = ? WHERE hash = 'c1'", (real_hash,))
    raw_conn.commit()

    result = repositories.get_commit_diff("o__r", real_hash)

    assert result is not None
    assert "diff --git a/a.txt b/a.txt" in result["diff"]


def test_explain_commit_diff_returns_none_when_diff_not_available(data_dir):
    seed_repo(data_dir, "o__r")

    result = repositories.explain_commit_diff("o__r", "0000000000000000000000000000000000000000")

    assert result is None


def test_explain_commit_diff_passes_real_diff_and_commit_message_to_llm(data_dir, monkeypatch):
    import sqlite3
    import subprocess

    import src.llm.groq_client as groq_client

    seed_repo(data_dir, "o__r")
    clone_dir = data_dir / "raw" / "_clones" / "o__r"
    clone_dir.mkdir(parents=True)
    run = lambda *args: subprocess.run(["git", "-C", str(clone_dir), *args], check=True, capture_output=True)
    run("init", "-b", "main")
    run("config", "user.name", "Alice")
    run("config", "user.email", "alice@example.com")
    (clone_dir / "a.txt").write_text("hello\n")
    run("add", "a.txt")
    run("commit", "-m", "Initial commit")
    real_hash = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()

    raw_conn = sqlite3.connect(str(data_dir / "raw" / "o__r.db"))
    raw_conn.execute("UPDATE commits SET hash = ?, message = 'Initial commit' WHERE hash = 'c1'", (real_hash,))
    raw_conn.commit()

    captured = {}

    def fake_explain_diff(commit_message, diff_text, session=None, model=None):
        captured["commit_message"] = commit_message
        captured["diff_text"] = diff_text
        return "This adds a.txt."

    monkeypatch.setattr(groq_client, "explain_diff", fake_explain_diff)

    result = repositories.explain_commit_diff("o__r", real_hash)

    assert result == {"explanation": "This adds a.txt."}
    assert captured["commit_message"] == "Initial commit"
    assert "diff --git a/a.txt b/a.txt" in captured["diff_text"]


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
