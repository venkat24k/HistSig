"""Phase 2 orchestration: compute P and R features for every candidate
event of one repository, across both granularities, and persist them."""

import sqlite3

from src.features.p_features import (
    compute_churn,
    compute_comment_count,
    compute_distinct_commenters,
    compute_files_changed,
    compute_issue_has_label,
    compute_issue_link_present,
    compute_reaction_count,
    compute_release_proximity,
    compute_review_rounds,
    compute_reviewer_count,
)
from src.features.r_features import (
    build_file_touch_index,
    compute_files_survived,
    compute_later_references_count,
    compute_maturity,
    compute_releases_since_count,
    compute_subsequent_modification_count,
)
from src.features.storage import insert_p_features, insert_r_features

# (feature name, compute function) — add a new feature here plus its column
# name in storage.py's _FEATURE_COLUMNS; nothing else needs to change.
_P_FEATURES = [
    ("comment_count", compute_comment_count),
    ("distinct_commenters", compute_distinct_commenters),
    ("reviewer_count", compute_reviewer_count),
    ("review_rounds", compute_review_rounds),
    ("files_changed", compute_files_changed),
    ("churn", compute_churn),
    ("issue_link_present", compute_issue_link_present),
    ("issue_has_label", compute_issue_has_label),
    ("release_proximity", compute_release_proximity),
    ("reaction_count", compute_reaction_count),
]


def extract_p_features(raw_conn: sqlite3.Connection, processed_conn: sqlite3.Connection, repo_id: int) -> dict:
    events = processed_conn.execute(
        "SELECT id, event_type, source_pr_number, primary_commit_hash, occurred_at FROM candidate_events WHERE repo_id = ?", (repo_id,)
    ).fetchall()

    rows = []
    for event_id, event_type, source_pr_number, primary_commit_hash, occurred_at in events:
        row = {"event_id": event_id}
        for name, compute in _P_FEATURES:
            value, status = compute(raw_conn, repo_id, event_type, source_pr_number, primary_commit_hash, occurred_at)
            row[name] = value
            row[f"{name}_status"] = status
        rows.append(row)

    insert_p_features(processed_conn, repo_id, rows)

    summary = {"events_processed": len(rows)}
    for name, _ in _P_FEATURES:
        counts: dict[str, int] = {}
        for r in rows:
            counts[r[f"{name}_status"]] = counts.get(r[f"{name}_status"], 0) + 1
        summary[f"{name}_by_status"] = counts
    return summary


def extract_r_features(raw_conn: sqlite3.Connection, processed_conn: sqlite3.Connection, repo_id: int) -> dict:
    """Most R features need only processed_conn — Stage 2's file-identity
    tables, repository_data_availability, and Stage 3's commit_level
    candidate events already carry what they read. raw_conn is only for
    releases_since_count, which reads the releases table Stage 1 collects
    and Stage 2 never copies forward (same reason P's release_proximity
    needs raw_conn)."""
    avail = processed_conn.execute(
        "SELECT earliest_commit_date, latest_commit_date FROM repository_data_availability WHERE repo_id = ?", (repo_id,)
    ).fetchone()
    earliest_commit_date, latest_commit_date = avail if avail else (None, None)

    events = processed_conn.execute(
        "SELECT id, event_type, source_pr_number, occurred_at FROM candidate_events WHERE repo_id = ?", (repo_id,)
    ).fetchall()

    # Built once per repo rather than once per event — see
    # build_file_touch_index's docstring for why the per-event query path
    # doesn't scale (it re-scans a popular file's whole touch history from
    # scratch for every event that happens to touch it).
    file_touch_index = build_file_touch_index(processed_conn, repo_id)

    rows = []
    for event_id, event_type, source_pr_number, occurred_at in events:
        maturity, maturity_status = compute_maturity(earliest_commit_date, latest_commit_date, occurred_at)
        files_survived, files_survived_status = compute_files_survived(processed_conn, repo_id, event_id)
        subsequent_modification_count, subsequent_modification_count_status = compute_subsequent_modification_count(
            processed_conn, repo_id, event_id, occurred_at, file_touch_index=file_touch_index
        )
        releases_since_count, releases_since_count_status = compute_releases_since_count(raw_conn, repo_id, occurred_at)
        later_references_count, later_references_count_status = compute_later_references_count(
            raw_conn, repo_id, event_type, source_pr_number, occurred_at
        )
        rows.append({
            "event_id": event_id,
            "maturity": maturity, "maturity_status": maturity_status,
            "files_survived": files_survived, "files_survived_status": files_survived_status,
            "subsequent_modification_count": subsequent_modification_count,
            "subsequent_modification_count_status": subsequent_modification_count_status,
            "releases_since_count": releases_since_count,
            "releases_since_count_status": releases_since_count_status,
            "later_references_count": later_references_count,
            "later_references_count_status": later_references_count_status,
        })

    insert_r_features(processed_conn, repo_id, rows)

    summary = {"events_processed": len(rows)}
    for name in ("maturity", "files_survived", "subsequent_modification_count", "releases_since_count", "later_references_count"):
        counts: dict[str, int] = {}
        for r in rows:
            counts[r[f"{name}_status"]] = counts.get(r[f"{name}_status"], 0) + 1
        summary[f"{name}_by_status"] = counts
    return summary
