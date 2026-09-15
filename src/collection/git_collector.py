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

import datetime
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
    author_date_utc: str | None
    committer_name: str | None
    committer_email: str | None
    committer_date: str | None
    committer_date_utc: str | None
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

    `-c core.longpaths=true` is passed on every command that writes the
    working tree (clone, reset --hard): Windows defaults to a 260-character
    MAX_PATH, and some real repositories have file paths that exceed it
    (confirmed against pallets/streamlit — `e2e_playwright/__snapshots__/...`
    test-snapshot filenames run well past it). Without this flag, `git
    clone` reports success at the object-transfer level but then fails to
    check out those specific files ("unable to create file ...: Filename
    too long") and the whole command still exits non-zero — this flag is
    git's own opt-in workaround and needs no elevated permissions or global
    git config change, unlike the Windows-wide `LongPathsEnabled` registry
    setting some guides suggest instead.
    """
    clone_path = Path(clone_dir)
    if (clone_path / ".git").exists():
        subprocess.run(
            ["git", "-C", str(clone_path), "-c", "core.longpaths=true", "fetch", "--all", "--tags", "--quiet"],
            check=True, timeout=timeout_seconds, env=_GIT_ENV,
        )
        subprocess.run(
            ["git", "-C", str(clone_path), "-c", "core.longpaths=true", "reset", "--hard", "--quiet", "@{u}"],
            check=True, timeout=timeout_seconds, env=_GIT_ENV,
        )
    else:
        clone_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "-c", "core.longpaths=true", "clone", "--quiet", remote_url, str(clone_path)],
            check=True, timeout=timeout_seconds, env=_GIT_ENV,
        )
    return str(clone_path)


def get_commit_diff(clone_dir: str, commit_hash: str, max_chars: int = 200_000) -> dict | None:
    """The real unified diff for one commit, read directly from the local
    git clone on demand — never stored in the database. This is
    deliberately a read path, not a Stage 1 collection step: diffs can be
    large, most are never looked at, and the local clone `ensure_local_clone`
    already keeps around is sufficient evidence to regenerate one whenever
    a user actually wants to inspect it (CLAUDE.md Section 21: correctness/
    simplicity before scale — don't pay the storage cost until there's a
    concrete need). This is exactly the "inspect evidence behind a
    ranking" capability from CLAUDE.md Section 8/10 — real code, no LLM
    involved in producing or interpreting it.

    Returns `None` if the clone directory doesn't exist locally (a repo
    collected before its clone was kept, or the clone was since removed)
    — the caller is expected to only call this for a commit hash it
    already knows is present in the raw `commits` table, so a `None` here
    means "we have the metadata but not the clone to regenerate the diff
    from," the same kind of gap `files_survived`/`compute_diff` elsewhere
    in this project already represents as a real, named absence rather
    than an error.

    `--format=""` on `git show` suppresses the commit-message header
    (already shown elsewhere in the UI from the `commits` table), leaving
    just the diff itself. A merge commit still produces real output here
    (git's own default condensed "diff --cc" against both parents) —
    deliberately not special-cased to match the plain-diff case, since
    that's still real, inspectable evidence, just of a different shape.

    Truncated to `max_chars` (a very large or generated-file diff could
    otherwise return megabytes) — `truncated` tells the caller so the UI
    can say so rather than silently showing a cut-off diff as if it were
    complete."""
    clone_path = Path(clone_dir)
    if not (clone_path / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(clone_path), "show", "--no-color", "--format=", commit_hash],
            capture_output=True, text=True, timeout=30, env=_GIT_ENV, check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None

    diff_text = result.stdout.lstrip("\n")
    truncated = len(diff_text) > max_chars
    return {"diff": diff_text[:max_chars] if truncated else diff_text, "truncated": truncated}


def _looks_like_remote(path_to_repo: str) -> bool:
    return "://" in path_to_repo or path_to_repo.startswith("git@")


def _to_posix(path: str | None) -> str | None:
    return path.replace("\\", "/") if path is not None else None


def _to_utc_isoformat(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).isoformat()


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
                # mf.filename is only the basename (e.g. "__init__.py"),
                # which collides across directories and doesn't line up
                # with mf.old_path (a full path) for rename tracking. Use
                # the full relative path on both sides instead: new_path
                # for anything but a delete, old_path for a delete (where
                # new_path is None). PyDriller returns these through
                # pathlib.Path, which normalizes to OS-native separators —
                # forced back to "/" here so the same repository produces
                # identical raw data regardless of which OS the collector
                # runs on (CLAUDE.md Section 13: reproducibility).
                filename=_to_posix(mf.new_path if mf.new_path is not None else mf.old_path),
                old_path=_to_posix(mf.old_path),
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
                author_date_utc=_to_utc_isoformat(commit.author_date),
                committer_name=commit.committer.name,
                committer_email=commit.committer.email,
                committer_date=commit.committer_date.isoformat(),
                committer_date_utc=_to_utc_isoformat(commit.committer_date),
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
