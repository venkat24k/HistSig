"""CLI entry point: Phase 4 — classify every fully-scored candidate event
into one of CLAUDE.md Section 3's four P/R quadrants.

Usage:
    python scripts/compute_divergence.py --processed-db data/processed/<name>.db

Requires scripts/compute_p_scores.py and scripts/compute_r_scores.py to
have both already run against --processed-db. Safe to re-run. See
src/divergence/classify.py for the classification rule — it reuses the
is_high_p/is_high_r flags Phase 3 already computed, no new threshold or
category is introduced here.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.divergence.classify import classify_divergence
from src.divergence.schema import reset_schema as reset_divergence_schema
from src.divergence.storage import insert_divergence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-db", required=True, help="Path to the processed SQLite file (P and R scores already computed)")
    args = parser.parse_args()

    processed_conn = sqlite3.connect(args.processed_db)
    processed_conn.execute("PRAGMA foreign_keys = ON")

    repo_id_row = processed_conn.execute("SELECT DISTINCT repo_id FROM event_p_scores").fetchone()
    if repo_id_row is None:
        raise SystemExit(f"{args.processed_db} has no event_p_scores rows — run scripts/compute_p_scores.py first.")
    repo_id = repo_id_row[0]

    reset_divergence_schema(processed_conn)

    print(f"Classifying divergence for repo_id={repo_id}...")
    result = classify_divergence(processed_conn, repo_id)
    insert_divergence(processed_conn, repo_id, result["rows"])

    print(json.dumps(result["summary"], indent=2))
    print(f"Done. Classification stored in {args.processed_db}")


if __name__ == "__main__":
    main()
