"""CLI entry point: collect Git-level history for one repository into SQLite.

Usage:
    python scripts/collect_git_history.py --repo-url <git-url> --db-path data/raw/<name>.db

GitHub-specific evidence (issues, PRs, reviews, releases) is not collected
by this script yet — that is the next piece of Stage 1
(src/collection/github_collector.py), which needs GITHUB_TOKEN.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.collection.git_collector import collect_git_history
from src.collection.schema import connect
from src.collection.storage import insert_commits, upsert_repository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-url", required=True, help="Local path or remote URL PyDriller/Git can read")
    parser.add_argument("--repo-name", required=False, help="Defaults to the last path segment of --repo-url")
    parser.add_argument("--db-path", required=True, help="SQLite file to write raw evidence into")
    parser.add_argument("--branch", required=False, default=None, help="Restrict collection to one branch")
    args = parser.parse_args()

    repo_name = args.repo_name or args.repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")

    conn = connect(args.db_path)
    repo_id = upsert_repository(conn, url=args.repo_url, name=repo_name)

    commits = collect_git_history(args.repo_url, only_in_branch=args.branch)
    insert_commits(conn, repo_id, commits)

    print(f"Collected {len(commits)} commits for '{repo_name}' into {args.db_path}")


if __name__ == "__main__":
    main()
