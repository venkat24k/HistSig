"""CLI entry point: Phase 2 (second half) — extract P features for every
candidate event of a repository.

Usage:
    python scripts/extract_features.py --raw-db data/raw/<name>.db --processed-db data/processed/<name>.db

Requires Stage 3 (form_events.py) to have already run against
--processed-db. Safe to re-run.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.features.extract import extract_p_features
from src.features.schema import reset_schema as reset_features_schema


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-db", required=True, help="Path to the raw evidence SQLite file from Stage 1")
    parser.add_argument("--processed-db", required=True, help="Path to the processed SQLite file from Stage 2/3")
    args = parser.parse_args()

    raw_conn = sqlite3.connect(args.raw_db)
    repo_row = raw_conn.execute("SELECT id, name FROM repositories").fetchone()
    if repo_row is None:
        raise SystemExit(f"{args.raw_db} has no repository row — run Stage 1 collection first.")
    repo_id, repo_name = repo_row

    processed_conn = sqlite3.connect(args.processed_db)
    processed_conn.execute("PRAGMA foreign_keys = ON")
    reset_features_schema(processed_conn)
    event_count = processed_conn.execute("SELECT COUNT(*) FROM candidate_events WHERE repo_id = ?", (repo_id,)).fetchone()[0]
    if event_count == 0:
        raise SystemExit(f"{args.processed_db} has no candidate events for repo_id={repo_id} — run Stage 3 form_events.py first.")

    print(f"Extracting P features for {repo_name} (repo_id={repo_id})...")
    summary = extract_p_features(raw_conn, processed_conn, repo_id)

    print(json.dumps(summary, indent=2))
    print(f"Done. Feature values stored in {args.processed_db}")


if __name__ == "__main__":
    main()
