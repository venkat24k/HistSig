"""Integration coverage for src/pipeline.py's non-"collect" stages: given
raw evidence already on disk, does run_full_pipeline actually take a
repository all the way from normalize through P/R feature extraction,
P/R scoring, and divergence classification -- the chain the "Analyze
repository" flow (src/api/jobs.py) now runs by default for any repo, not
just the ones scripts/*.py happened to be run against by hand.

"collect" itself needs live network access and is intentionally excluded
here (matches every other test in this suite being offline) -- these
tests start from already-collected raw evidence, seeded directly against
the real Stage 1 schema, the same pattern tests/processing/test_normalize.py
already uses.
"""

import sqlite3

import pytest

from src.collection.schema import create_schema as create_raw_schema
from src.pipeline import DEFAULT_STAGES, run_full_pipeline

REPO_URL = "https://github.com/o/r"


def _seed_raw_db(path) -> None:
    conn = sqlite3.connect(str(path))
    create_raw_schema(conn)
    conn.execute(
        "INSERT INTO repositories (id, url, name, default_branch, collected_at) VALUES (1, ?, 'o/r', 'main', '2024-01-01')",
        (REPO_URL,),
    )
    conn.execute(
        "INSERT INTO commits (repo_id, hash, author_name, author_email, author_date, author_date_utc, message, is_merge, parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, 'c1', 'Alice', 'alice@example.com', '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z', 'Add feature', 0, '', 5, 1, 1)"
    )
    conn.execute(
        "INSERT INTO commit_files (repo_id, commit_hash, filename, old_path, change_type, insertions, deletions) "
        "VALUES (1, 'c1', 'a.py', NULL, 'ADD', 5, 1)"
    )
    conn.execute(
        "INSERT INTO pull_requests (id, repo_id, number, title, body, state, author_login, created_at, merged_at, closed_at, updated_at, base_branch, head_branch, merge_commit_sha) "
        "VALUES (1, 1, 1, 'Add feature', '', 'merged', 'alice', '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', '2024-01-01T01:00:00Z', '2024-01-01T01:00:00Z', 'main', 'feature', 'c1')"
    )
    conn.execute("INSERT INTO pr_commits (pr_id, commit_hash) VALUES (1, 'c1')")
    conn.execute(
        "INSERT INTO releases (id, repo_id, tag_name, name, created_at, published_at, author_login, body) "
        "VALUES (1, 1, 'v1.0', 'v1.0', '2024-02-01T00:00:00Z', '2024-02-01T00:00:00Z', 'alice', '')"
    )
    conn.commit()
    conn.close()


def test_run_full_pipeline_runs_every_non_collect_stage_by_default(tmp_path):
    raw_db_path = tmp_path / "raw.db"
    processed_db_path = tmp_path / "processed.db"
    _seed_raw_db(raw_db_path)

    stages = tuple(s for s in DEFAULT_STAGES if s != "collect")
    progress_log: list[str] = []

    result = run_full_pipeline(
        repo_url=REPO_URL, raw_db_path=str(raw_db_path), token="unused",
        processed_db_path=str(processed_db_path), stages=stages,
        on_progress=lambda stage, data: progress_log.append(stage),
    )

    assert result["repo_id"] == 1
    for key in ("normalize", "events", "p_features", "r_features", "p_scores", "r_scores", "divergence"):
        assert key in result, f"run_full_pipeline result missing {key!r} stage summary"

    processed_conn = sqlite3.connect(str(processed_db_path))
    assert processed_conn.execute("SELECT COUNT(*) FROM candidate_events").fetchone()[0] > 0
    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_features").fetchone()[0] > 0
    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_features").fetchone()[0] > 0
    assert processed_conn.execute("SELECT COUNT(*) FROM event_p_scores").fetchone()[0] > 0
    assert processed_conn.execute("SELECT COUNT(*) FROM event_r_scores").fetchone()[0] > 0
    # event_divergence must exist and be queryable even if nothing in
    # this tiny fixture happened to clear the "high" threshold.
    processed_conn.execute("SELECT COUNT(*) FROM event_divergence").fetchone()

    for expected_stage in [
        "extracting_p_features", "extracted_p_features",
        "extracting_r_features", "extracted_r_features",
        "scoring_p", "scored_p", "scoring_r", "scored_r",
        "classifying_divergence", "classified_divergence", "done",
    ]:
        assert expected_stage in progress_log, f"progress callback never saw stage {expected_stage!r}"


def test_run_full_pipeline_is_safe_to_rerun(tmp_path):
    # Re-running the full non-collect chain against the same dbs (e.g. a
    # user clicking "Analyze" again after new commits landed) must not
    # duplicate rows -- every stage's reset/idempotency behavior chained
    # together, not just each one in isolation.
    raw_db_path = tmp_path / "raw.db"
    processed_db_path = tmp_path / "processed.db"
    _seed_raw_db(raw_db_path)

    stages = tuple(s for s in DEFAULT_STAGES if s != "collect")
    run_full_pipeline(repo_url=REPO_URL, raw_db_path=str(raw_db_path), token="unused", processed_db_path=str(processed_db_path), stages=stages)
    run_full_pipeline(repo_url=REPO_URL, raw_db_path=str(raw_db_path), token="unused", processed_db_path=str(processed_db_path), stages=stages)

    processed_conn = sqlite3.connect(str(processed_db_path))
    events = processed_conn.execute("SELECT COUNT(*) FROM candidate_events").fetchone()[0]
    p_features = processed_conn.execute("SELECT COUNT(*) FROM event_p_features").fetchone()[0]
    p_scores = processed_conn.execute("SELECT COUNT(*) FROM event_p_scores").fetchone()[0]

    assert p_features == events
    assert p_scores == events


def test_run_full_pipeline_requires_processed_db_path_for_processed_stages(tmp_path):
    raw_db_path = tmp_path / "raw.db"
    _seed_raw_db(raw_db_path)

    with pytest.raises(ValueError):
        run_full_pipeline(repo_url=REPO_URL, raw_db_path=str(raw_db_path), token="unused", stages=("p_scores",))
