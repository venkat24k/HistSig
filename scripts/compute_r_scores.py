"""CLI entry point: Phase 3 (second half, R-only) — compute a composite
R(e) score for every candidate event and flag the top `--top-percentile`
fraction of each (granularity, event_type) group as high-R.

Usage:
    python scripts/compute_r_scores.py --processed-db data/processed/<name>.db [--top-percentile 0.10] [--min-maturity 0.05]

Requires scripts/extract_r_features.py to have already run against
--processed-db. Safe to re-run. See src/scoring/r_score.py for the
scoring method — identical to P's (src/scoring/p_score.py), except
`maturity` is deliberately excluded from the averaged features, and
events below `--min-maturity` are excluded from ranking entirely (too
young to have had a fair chance to accumulate R signal).
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring.r_score import MIN_MATURITY_FOR_SCORING, compute_r_scores
from src.scoring.schema import reset_r_schema as reset_r_scoring_schema
from src.scoring.storage import insert_r_scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-db", required=True, help="Path to the processed SQLite file (Stage 2/3 + R features already run)")
    parser.add_argument("--top-percentile", type=float, default=0.10, help="Fraction of each group flagged high-R (default 0.10 = top 10%%)")
    parser.add_argument(
        "--min-maturity", type=float, default=MIN_MATURITY_FOR_SCORING,
        help=f"Events with maturity below this (or unknown maturity) are excluded from ranking (default {MIN_MATURITY_FOR_SCORING})",
    )
    args = parser.parse_args()

    processed_conn = sqlite3.connect(args.processed_db)
    processed_conn.execute("PRAGMA foreign_keys = ON")

    repo_id_row = processed_conn.execute("SELECT DISTINCT repo_id FROM event_r_features").fetchone()
    if repo_id_row is None:
        raise SystemExit(f"{args.processed_db} has no event_r_features rows — run scripts/extract_r_features.py first.")
    repo_id = repo_id_row[0]

    reset_r_scoring_schema(processed_conn)

    print(f"Computing R scores for repo_id={repo_id} (top {args.top_percentile:.0%} per group flagged high-R, min maturity {args.min_maturity:.0%})...")
    result = compute_r_scores(processed_conn, repo_id, top_percentile=args.top_percentile, min_maturity=args.min_maturity)
    insert_r_scores(processed_conn, repo_id, result["score_rows"], result["threshold_rows"])

    print(json.dumps(result["summary"], indent=2))
    print(f"Done. Scores stored in {args.processed_db}")


if __name__ == "__main__":
    main()
