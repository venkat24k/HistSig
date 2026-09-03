"""Git-level collection using PyDriller.

Extracts commits, authors, timestamps, messages, and changed files directly
from Git history. This does not require GitHub API access or a token — it
works against any local clone Git can reach. Issues, pull requests,
reviews, and releases are collected separately in github_collector.py,
since they come from the GitHub API rather than Git itself.

`collect_git_history` deliberately only accepts a local path, not a remote
URL: handing PyDriller a remote URL directly was observed to hang
indefinitely on this project (no progress, no CPU use, no network calls) —
likely something in PyDriller/GitPython's own clone handling on Windows. A
plain `git clone` of the same URL completes in seconds, so `ensure_local_clone`
does that ourselves first, and PyDriller only ever operates on the resulting
local path.
"""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pydriller import Repository

# Force git to fail fast instead of blocking on an interactive credential
# prompt if authentication is ever unexpectedly required.
_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


@dataclass
class FileChangeRecord:
    filename: str | None
    old_path: str | None
    change_type: str
    insertions: int
    deletions: int


@dataclass
class CommitRecord:
    hash: str
    author_name: str | None
    author_email: str | None
    author_date: str | None
    committer_name: str | None
    committer_email: str | None
    committer_date: str | None
    message: str
    is_merge: bool
    parent_hashes: list[str]
    insertions: int
    deletions: int
    files_changed_count: int
    files: list[FileChangeRecord] = field(default_factory=list)


def ensure_local_clone(remote_url: str, clone_dir: str, timeout_seconds: int = 300) -> str:
    """Clone `remote_url` into `clone_dir` if not already present, else fetch
    updates into the existing clone. Returns `clone_dir`. Safe to call
    repeatedly (re-running collection only pays for a fetch, not a full
    re-clone).

    On an existing clone, `git fetch` alone updates the remote-tracking refs
    (`origin/<branch>`) but leaves the locally checked-out branch — and
    therefore `HEAD`, which is what PyDriller walks by default — exactly
    where it was. Without the `reset --hard @{u}` below, re-running
    collection against a repository that gained new commits since the first
    clone would silently return the same, now-stale commit list every time,
    which defeats the entire point of a "safe to re-run and stay current"
    collector.
    """
    clone_path = Path(clone_dir)
    if (clone_path / ".git").exists():
        subprocess.run(
            ["git", "-C", str(clone_path), "fetch", "--all", "--tags", "--quiet"],
            check=True, timeout=timeout_seconds, env=_GIT_ENV,
        )
        subprocess.run(
            ["git", "-C", str(clone_path), "reset", "--hard", "--quiet", "@{u}"],
            check=True, timeout=timeout_seconds, env=_GIT_ENV,
        )
    else:
        clone_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--quiet", remote_url, str(clone_path)],
            check=True, timeout=timeout_seconds, env=_GIT_ENV,
        )
    return str(clone_path)


def _looks_like_remote(path_to_repo: str) -> bool:
    return "://" in path_to_repo or path_to_repo.startswith("git@")


def collect_git_history(path_to_repo: str, only_in_branch: str | None = None) -> list[CommitRecord]:
    """Traverse a repository's Git history and return one CommitRecord per commit.

    `path_to_repo` must be a local path (see module docstring for why remote
    URLs aren't accepted directly) — use `ensure_local_clone` first for a
    remote repository. A remote-looking argument raises immediately rather
    than being handed to PyDriller, which was observed to hang indefinitely
    instead of failing on one (see module docstring).
    """
    if _looks_like_remote(path_to_repo):
        raise ValueError(
            f"collect_git_history requires a local path, got what looks like a remote URL: {path_to_repo!r}. "
            "Call ensure_local_clone(remote_url, clone_dir) first and pass its return value here instead."
        )

    kwargs = {}
    if only_in_branch:
        kwargs["only_in_branch"] = only_in_branch

    records: list[CommitRecord] = []
    for commit in Repository(path_to_repo, **kwargs).traverse_commits():
        files = [
            FileChangeRecord(
                filename=mf.filename,
                old_path=mf.old_path,
                change_type=mf.change_type.name,
                insertions=mf.added_lines,
                deletions=mf.deleted_lines,
            )
            for mf in commit.modified_files
        ]
        records.append(
            CommitRecord(
                hash=commit.hash,
                author_name=commit.author.name,
                author_email=commit.author.email,
                author_date=commit.author_date.isoformat(),
                committer_name=commit.committer.name,
                committer_email=commit.committer.email,
                committer_date=commit.committer_date.isoformat(),
                message=commit.msg,
                is_merge=commit.merge,
                parent_hashes=list(commit.parents),
                insertions=commit.insertions,
                deletions=commit.deletions,
                files_changed_count=commit.files,
                files=files,
            )
        )
    return records
