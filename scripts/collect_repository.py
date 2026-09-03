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
import re
import sys
from concurrent.futures import ThreadPoolExecutor
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

# Matches the owner/repo segment right after "github.com" for both HTTPS
# (https://github.com/owner/repo[.git][/]) and SSH (git@github.com:owner/repo.git)
# URLs, and ignores anything after it (e.g. a browser-pasted
# .../owner/repo/tree/main URL) rather than silently misparsing it.
_GITHUB_URL_RE = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?(?:/|$)")


def parse_owner_repo(url: str) -> str:
    match = _GITHUB_URL_RE.search(url.strip())
    if not match:
        raise ValueError(f"Could not parse an owner/repo from {url!r} — expected a github.com HTTPS or SSH URL.")
    return f"{match.group(1)}/{match.group(2)}"


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

    # Git history (local, subprocess/CPU-bound) and the three GraphQL
    # collectors (network-bound, independent of each other and of the git
    # walk) have no data dependency on one another, so they run concurrently
    # rather than paying the sum of four sequential stages. Each collector
    # still does its own internal pagination sequentially; only these four
    # top-level stages overlap. Database writes stay on the main thread
    # (sqlite3 connections aren't safe to share across threads) — each
    # insert runs only after its collector has fully returned.
    print(f"Collecting commits, issues, pull requests, and releases for {owner_repo}...")
    collectors = {
        "commits": lambda: collect_git_history(local_path, only_in_branch=args.branch),
        "issues": lambda: collect_issues(session, owner_repo),
        "pull_requests": lambda: collect_pull_requests(session, owner_repo),
        "releases": lambda: collect_releases(session, owner_repo),
    }
    with ThreadPoolExecutor(max_workers=len(collectors)) as pool:
        futures = {name: pool.submit(fn) for name, fn in collectors.items()}
        results = {name: future.result() for name, future in futures.items()}

    insert_commits(conn, repo_id, results["commits"])
    print(f"  {len(results['commits'])} commits")
    insert_issues(conn, repo_id, results["issues"])
    print(f"  {len(results['issues'])} issues")
    insert_pull_requests(conn, repo_id, results["pull_requests"])
    print(f"  {len(results['pull_requests'])} pull requests")
    insert_releases(conn, repo_id, results["releases"])
    print(f"  {len(results['releases'])} releases")

    print(f"Done. Raw evidence stored in {args.db_path}")


if __name__ == "__main__":
    main()
