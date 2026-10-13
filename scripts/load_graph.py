"""CLI entry point: Stage 8 (iteration 1) — load one repo's events, authors,
and touched files into Neo4j as a knowledge graph.

Usage:
    python scripts/load_graph.py --processed-db data/processed/<name>.db --safe-name <owner>__<repo> \
        [--granularity pr_bundle] [--clear]

Requires NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD in the environment (see
.env.example) and a reachable Neo4j instance. Requires the processed db to
already have events (and ideally P/R scores + divergence) computed — this
stage is a pure transform of already-computed data, not new methodology.

--clear wipes this repo's existing slice of the graph first (safe to
re-run; does not touch any other repo already loaded into the same shared
Neo4j database).
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.graph.build import load_repo
from src.graph.schema import clear_repo, create_schema


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--processed-db", required=True)
    parser.add_argument("--safe-name", required=True, help="e.g. pallets__markupsafe")
    parser.add_argument("--granularity", default="pr_bundle", choices=["pr_bundle", "commit_level"])
    parser.add_argument("--clear", action="store_true", help="Delete this repo's existing graph slice first")
    args = parser.parse_args()

    load_dotenv()
    uri = os.environ.get("NEO4J_URI")
    username = os.environ.get("NEO4J_USERNAME")
    password = os.environ.get("NEO4J_PASSWORD")
    if not (uri and username and password):
        raise SystemExit("NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD must be set (see .env.example)")

    driver = GraphDatabase.driver(uri, auth=(username, password))
    create_schema(driver)

    if args.clear:
        print(f"Clearing existing graph slice for {args.safe_name}...")
        clear_repo(driver, args.safe_name)

    processed_conn = sqlite3.connect(args.processed_db)
    print(f"Loading {args.safe_name} ({args.granularity}) into Neo4j...")
    summary = load_repo(driver, processed_conn, args.safe_name, granularity=args.granularity)
    driver.close()

    print(f"Done: {summary}")


if __name__ == "__main__":
    main()
