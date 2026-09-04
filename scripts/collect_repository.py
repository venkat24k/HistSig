"""CLI entry point: full Stage 1 collection (Git history + GitHub API
evidence) for one public GitHub repository into SQLite.

Usage:
    python scripts/collect_repository.py --repo https://github.com/<owner>/<repo> --db-path data/raw/<name>.db

Requires GITHUB_TOKEN (see .env.example) — loaded automatically from a
.env file in the project root if one exists. Re-running against the same
--db-path is safe (see src/collection/storage.py: all inserts are
idempotent). Thin wrapper around src.pipeline.run_full_pipeline (stage
"collect" only), which is also used by the API backend (src/api/) so the
two never drift apart.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.pipeline import run_full_pipeline


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="GitHub repository URL, e.g. https://github.com/owner/repo")
    parser.add_argument("--db-path", required=True, help="SQLite file to write raw evidence into")
    parser.add_argument("--branch", required=False, default=None, help="Restrict Git history collection to one branch")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set. Copy .env.example to .env and fill it in.")

    def on_progress(stage: str, data: dict) -> None:
        if stage == "cloning":
            print("Cloning/updating local mirror...")
        elif stage == "collecting":
            print("Collecting commits, issues, pull requests, and releases...")
        elif stage == "collected":
            print(f"  {data['count']} {data['entity']}")

    result = run_full_pipeline(
        repo_url=args.repo, raw_db_path=args.db_path, token=token,
        branch=args.branch, stages=("collect",), on_progress=on_progress,
    )

    print(f"Done. Raw evidence stored in {args.db_path} ({result['counts']})")


if __name__ == "__main__":
    main()
