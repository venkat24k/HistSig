"""CLI entry point: Stage 2 — normalize one repository's raw evidence into
data/processed/.

Usage:
    python scripts/normalize_repository.py --raw-db data/raw/<name>.db --processed-db data/processed/<name>.db

Read-only against the raw database; safe to re-run (each run fully
replaces that repository's processed rows — see storage.py).
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.processing.normalize import normalize_repository
from src.processing.schema import connect as connect_processed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-db", required=True, help="Path to the raw evidence SQLite file from Stage 1")
    parser.add_argument("--processed-db", required=True, help="SQLite file to write normalized evidence into")
    args = parser.parse_args()

    raw_conn = sqlite3.connect(args.raw_db)
    raw_conn.row_factory = sqlite3.Row
    repo_row = raw_conn.execute("SELECT id, name FROM repositories").fetchone()
    if repo_row is None:
        raise SystemExit(f"{args.raw_db} has no repository row — run Stage 1 collection first.")
    repo_id, repo_name = repo_row["id"], repo_row["name"]

    processed_conn = connect_processed(args.processed_db)

    print(f"Normalizing {repo_name} (repo_id={repo_id})...")
    summary = normalize_repository(raw_conn, processed_conn, repo_id)

    print(json.dumps(summary, indent=2))
    print(f"Done. Processed evidence stored in {args.processed_db}")


if __name__ == "__main__":
    main()
