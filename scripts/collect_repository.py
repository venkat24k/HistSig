"""CLI entry point: full Stage 1 collection (Git history + GitHub API
evidence) for one public GitHub repository into SQLite.

Usage:
    python scripts/collect_repository.py --repo https://github.com/<owner>/<repo> --db-path data/raw/<name>.db

Requires GITHUB_TOKEN (see .env.example) — loaded automatically from a
.env file in the project root if one exists. Re-running against the same
--db-path is safe (see src/collection/storage.py: all inserts are
idempotent).
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.collection.git_collector import collect_git_history, ensure_local_clone
from src.collection.github_collector import (
    collect_issues,
    collect_pull_requests,
    collect_releases,
    get_repo_metadata,
    get_session,
)
from src.collection.schema import connect
from src.collection.storage import insert_commits, insert_issues, insert_pull_requests, insert_releases, upsert_repository


def parse_owner_repo(url: str) -> str:
    """'https://github.com/owner/repo' or '.../repo.git' -> 'owner/repo'."""
    path = url.rstrip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return "/".join(path.split("/")[-2:])


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

    owner_repo = parse_owner_repo(args.repo)
    session = get_session(token)
    repo_meta = get_repo_metadata(session, owner_repo)

    conn = connect(args.db_path)
    repo_id = upsert_repository(conn, url=args.repo, name=owner_repo, default_branch=repo_meta.get("default_branch"))

    clone_dir = Path("data/raw/_clones") / owner_repo.replace("/", "__")
    print(f"Cloning/updating local mirror of {owner_repo} at {clone_dir}...")
    local_path = ensure_local_clone(repo_meta["clone_url"], str(clone_dir))

    print(f"Collecting Git history for {owner_repo}...")
    commits = collect_git_history(local_path, only_in_branch=args.branch)
    insert_commits(conn, repo_id, commits)
    print(f"  {len(commits)} commits")

    print(f"Collecting issues for {owner_repo}...")
    issues = collect_issues(session, owner_repo)
    insert_issues(conn, repo_id, issues)
    print(f"  {len(issues)} issues")

    print(f"Collecting pull requests for {owner_repo}...")
    pull_requests = collect_pull_requests(session, owner_repo)
    insert_pull_requests(conn, repo_id, pull_requests)
    print(f"  {len(pull_requests)} pull requests")

    print(f"Collecting releases for {owner_repo}...")
    releases = collect_releases(session, owner_repo)
    insert_releases(conn, repo_id, releases)
    print(f"  {len(releases)} releases")

    print(f"Done. Raw evidence stored in {args.db_path}")


if __name__ == "__main__":
    main()
