"""CLI entry point: Phase 3 (first half, P-only) — compute a composite
P(e) score for every candidate event and flag the top `--top-percentile`
fraction of each (granularity, event_type) group as high-P.

Usage:
    python scripts/compute_p_scores.py --processed-db data/processed/<name>.db [--top-percentile 0.10]

Requires scripts/extract_features.py to have already run against
--processed-db. Safe to re-run. See src/scoring/p_score.py for the
scoring method and why it was chosen.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring.p_score import compute_p_scores
from src.scoring.schema import reset_schema as reset_scoring_schema
from src.scoring.storage import insert_p_scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-db", required=True, help="Path to the processed SQLite file (Stage 2/3 + P features already run)")
    parser.add_argument("--top-percentile", type=float, default=0.10, help="Fraction of each group flagged high-P (default 0.10 = top 10%%)")
    args = parser.parse_args()

    processed_conn = sqlite3.connect(args.processed_db)
    processed_conn.execute("PRAGMA foreign_keys = ON")

    repo_id_row = processed_conn.execute("SELECT DISTINCT repo_id FROM event_p_features").fetchone()
    if repo_id_row is None:
        raise SystemExit(f"{args.processed_db} has no event_p_features rows — run scripts/extract_features.py first.")
    repo_id = repo_id_row[0]

    reset_scoring_schema(processed_conn)

    print(f"Computing P scores for repo_id={repo_id} (top {args.top_percentile:.0%} per group flagged high-P)...")
    result = compute_p_scores(processed_conn, repo_id, top_percentile=args.top_percentile)
    insert_p_scores(processed_conn, repo_id, result["score_rows"], result["threshold_rows"])

    print(json.dumps(result["summary"], indent=2))
    print(f"Done. Scores stored in {args.processed_db}")


if __name__ == "__main__":
    main()
