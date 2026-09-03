"""CLI entry point: collect Git-level history for one *local* repository
clone into SQLite — no GitHub API access or token required.

Usage:
    python scripts/collect_git_history.py --repo-path <local-path> --db-path data/raw/<name>.db

For a GitHub URL (which needs cloning first) plus issues/PRs/reviews/
releases, use scripts/collect_repository.py instead — that one clones the
repository itself and also collects GitHub API evidence, which needs
GITHUB_TOKEN. This script intentionally stays local-path-only rather than
also accepting a URL and cloning it, so there is exactly one place
(collect_repository.py / ensure_local_clone) responsible for turning a
remote URL into a local clone.
"""

import argparse
import os.path
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.collection.git_collector import collect_git_history
from src.collection.schema import connect
from src.collection.storage import insert_commits, upsert_repository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", required=True, help="Path to an existing local Git clone")
    parser.add_argument("--repo-name", required=False, help="Defaults to the folder name in --repo-path")
    parser.add_argument("--db-path", required=True, help="SQLite file to write raw evidence into")
    parser.add_argument("--branch", required=False, default=None, help="Restrict collection to one branch")
    args = parser.parse_args()

    repo_name = args.repo_name or os.path.basename(os.path.normpath(args.repo_path))

    conn = connect(args.db_path)
    repo_id = upsert_repository(conn, url=args.repo_path, name=repo_name)

    commits = collect_git_history(args.repo_path, only_in_branch=args.branch)
    insert_commits(conn, repo_id, commits)

    print(f"Collected {len(commits)} commits for '{repo_name}' into {args.db_path}")


if __name__ == "__main__":
    main()
