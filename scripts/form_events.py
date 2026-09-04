"""CLI entry point: Stage 3 — form candidate historical events from
normalized evidence.

Usage:
    python scripts/form_events.py --raw-db data/raw/<name>.db --processed-db data/processed/<name>.db

Requires Stage 2 (normalize_repository.py) to have already run against
--processed-db, since author resolution depends on its contributor
tables. Generates both supported granularities (pr_bundle, commit_level)
by default; safe to re-run.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.events.orchestrate import form_and_store_events
from src.events.schema import create_schema as create_events_schema


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-db", required=True, help="Path to the raw evidence SQLite file from Stage 1")
    parser.add_argument("--processed-db", required=True, help="Path to the processed SQLite file from Stage 2")
    parser.add_argument("--granularity", action="append", choices=["pr_bundle", "commit_level"],
                         help="Restrict to one granularity; repeatable. Defaults to both.")
    args = parser.parse_args()

    raw_conn = sqlite3.connect(args.raw_db)
    repo_row = raw_conn.execute("SELECT id, name FROM repositories").fetchone()
    if repo_row is None:
        raise SystemExit(f"{args.raw_db} has no repository row — run Stage 1 collection first.")
    repo_id, repo_name = repo_row

    processed_conn = sqlite3.connect(args.processed_db)
    processed_conn.execute("PRAGMA foreign_keys = ON")
    create_events_schema(processed_conn)
    contributor_count = processed_conn.execute("SELECT COUNT(*) FROM contributors WHERE repo_id = ?", (repo_id,)).fetchone()[0]
    if contributor_count == 0:
        raise SystemExit(f"{args.processed_db} has no contributors for repo_id={repo_id} — run Stage 2 normalize_repository.py first.")

    granularities = tuple(args.granularity) if args.granularity else None
    kwargs = {"granularities": granularities} if granularities else {}

    print(f"Forming candidate events for {repo_name} (repo_id={repo_id})...")
    summary = form_and_store_events(raw_conn, processed_conn, repo_id, **kwargs)

    print(json.dumps(summary, indent=2))
    print(f"Done. Candidate events stored in {args.processed_db}")


if __name__ == "__main__":
    main()
