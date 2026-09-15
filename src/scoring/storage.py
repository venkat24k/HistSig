"""Persistence for P-score and R-score results.

Same idempotency pattern as every prior stage: scoring is a deterministic
full derivation from event_p_features/event_r_features, so re-running it
for a repo clears and rewrites that repo's rows rather than trying to
diff/merge.
"""

import sqlite3


def insert_p_scores(processed_conn: sqlite3.Connection, repo_id: int, score_rows: list[tuple], threshold_rows: list[tuple]) -> None:
    """`score_rows`/`threshold_rows` are exactly the lists
    `src/scoring/p_score.py: compute_p_scores` returns under those keys."""
    processed_conn.execute("DELETE FROM event_p_scores WHERE repo_id = ?", (repo_id,))
    processed_conn.execute("DELETE FROM p_score_thresholds WHERE repo_id = ?", (repo_id,))

    if score_rows:
        processed_conn.executemany(
            """
            INSERT INTO event_p_scores (event_id, repo_id, granularity, event_type, p_score, features_used, is_high_p)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            score_rows,
        )
    if threshold_rows:
        processed_conn.executemany(
            """
            INSERT INTO p_score_thresholds (repo_id, granularity, event_type, top_percentile, threshold_score, group_size)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            threshold_rows,
        )
    processed_conn.commit()


def insert_r_scores(processed_conn: sqlite3.Connection, repo_id: int, score_rows: list[tuple], threshold_rows: list[tuple]) -> None:
    """Same shape/idempotency as insert_p_scores, for event_r_scores — see
    src/scoring/r_score.py: compute_r_scores."""
    processed_conn.execute("DELETE FROM event_r_scores WHERE repo_id = ?", (repo_id,))
    processed_conn.execute("DELETE FROM r_score_thresholds WHERE repo_id = ?", (repo_id,))

    if score_rows:
        processed_conn.executemany(
            """
            INSERT INTO event_r_scores (event_id, repo_id, granularity, event_type, r_score, features_used, is_high_r)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            score_rows,
        )
    if threshold_rows:
        processed_conn.executemany(
            """
            INSERT INTO r_score_thresholds (repo_id, granularity, event_type, top_percentile, threshold_score, group_size)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            threshold_rows,
        )
    processed_conn.commit()
