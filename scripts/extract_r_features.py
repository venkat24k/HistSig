"""CLI entry point: Phase 2 (third quarter) — extract R features for every
candidate event of a repository.

Usage:
    python scripts/extract_r_features.py --raw-db data/raw/<name>.db --processed-db data/processed/<name>.db

Requires Stage 2/3 (normalize_repository.py, form_events.py) to have
already run against --processed-db. Most R features only read the
processed database (file identities, repository_data_availability,
commit_level candidate events); --raw-db is needed for
releases_since_count, which reads the releases table Stage 1 collects
and Stage 2 never copies forward. Safe to re-run.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.events.schema import create_schema as create_events_schema
from src.features.extract import extract_r_features
from src.features.schema import reset_r_schema


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-db", required=True, help="Path to the raw evidence SQLite file from Stage 1")
    parser.add_argument("--processed-db", required=True, help="Path to the processed SQLite file from Stage 2/3")
    args = parser.parse_args()

    raw_conn = sqlite3.connect(args.raw_db)

    processed_conn = sqlite3.connect(args.processed_db)
    processed_conn.execute("PRAGMA foreign_keys = ON")
    # Re-applies events schema (idempotent: CREATE TABLE/INDEX IF NOT
    # EXISTS) so an index added to src/events/schema.py after a database
    # was first created still gets picked up here, not just on databases
    # built from scratch.
    create_events_schema(processed_conn)

    repo_id_row = processed_conn.execute("SELECT repo_id FROM repository_data_availability LIMIT 1").fetchone()
    if repo_id_row is None:
        raise SystemExit(f"{args.processed_db} has no repository_data_availability row — run Stage 2 normalize_repository.py first.")
    repo_id = repo_id_row[0]

    event_count = processed_conn.execute("SELECT COUNT(*) FROM candidate_events WHERE repo_id = ?", (repo_id,)).fetchone()[0]
    if event_count == 0:
        raise SystemExit(f"{args.processed_db} has no candidate events for repo_id={repo_id} — run Stage 3 form_events.py first.")

    reset_r_schema(processed_conn)

    print(f"Extracting R features for repo_id={repo_id}...")
    summary = extract_r_features(raw_conn, processed_conn, repo_id)

    print(json.dumps(summary, indent=2))
    print(f"Done. Feature values stored in {args.processed_db}")


if __name__ == "__main__":
    main()
