"""Persistence for divergence classification (Phase 4).

Same idempotency pattern as Stage 2/3 and Phase 2/3's own storage
modules: classification is a deterministic full derivation from
already-computed P/R scores, so re-running it for a repo clears and
rewrites that repo's rows.
"""

import sqlite3


def insert_divergence(processed_conn: sqlite3.Connection, repo_id: int, rows: list[dict]) -> None:
    processed_conn.execute("DELETE FROM event_divergence WHERE repo_id = ?", (repo_id,))
    processed_conn.executemany(
        """
        INSERT INTO event_divergence (event_id, repo_id, granularity, event_type, p_score, r_score, is_high_p, is_high_r, quadrant)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r["event_id"], repo_id, r["granularity"], r["event_type"],
                r["p_score"], r["r_score"], r["is_high_p"], r["is_high_r"], r["quadrant"],
            )
            for r in rows
        ],
    )
    processed_conn.commit()
