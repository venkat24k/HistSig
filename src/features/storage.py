"""Persistence for P/R feature values.

Same idempotency pattern as Stages 2-3: feature extraction is a
deterministic full derivation from raw + processed evidence, so re-running
it for a repo clears and rewrites that repo's feature rows.
"""

import sqlite3

_FEATURE_COLUMNS = ["comment_count", "distinct_commenters", "reviewer_count", "review_rounds", "files_changed", "churn", "issue_link_present", "issue_has_label", "release_proximity", "reaction_count"]


def insert_p_features(processed_conn: sqlite3.Connection, repo_id: int, rows: list[dict]) -> None:
    """`rows` is a list of dicts with "event_id" plus, per feature in
    _FEATURE_COLUMNS, a "<name>" value and "<name>_status" key (see
    src/features/p_features.py)."""
    columns = ["event_id", "repo_id"]
    for name in _FEATURE_COLUMNS:
        columns += [name, f"{name}_status"]

    processed_conn.execute("DELETE FROM event_p_features WHERE repo_id = ?", (repo_id,))
    processed_conn.executemany(
        f"INSERT INTO event_p_features ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        [
            (r["event_id"], repo_id, *[r[key] for name in _FEATURE_COLUMNS for key in (name, f"{name}_status")])
            for r in rows
        ],
    )
    processed_conn.commit()
