"""Phase 2 orchestration: compute P features for every candidate event of
one repository, across both granularities, and persist them."""

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
from src.features.storage import insert_p_features

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
