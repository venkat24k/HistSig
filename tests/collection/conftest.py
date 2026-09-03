"""Builds a tiny local Git repository with a known, fixed commit history.

Used by collection tests so they run fully offline and deterministically —
no network access or GitHub token is required (see CLAUDE.md Section 19:
tests must not depend on live network calls).
"""

import subprocess

import pytest


def _run(repo_path, *args):
    subprocess.run(["git", "-C", str(repo_path), *args], check=True, capture_output=True)


@pytest.fixture
def tmp_git_repo(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _run(repo_path, "init", "-b", "main")
    _run(repo_path, "config", "user.name", "Test Author")
    _run(repo_path, "config", "user.email", "author@example.com")

    (repo_path / "a.txt").write_text("first version\n")
    _run(repo_path, "add", "a.txt")
    _run(repo_path, "commit", "-m", "Add a.txt")

    (repo_path / "a.txt").write_text("first version\nsecond line\n")
    (repo_path / "b.txt").write_text("new file\n")
    _run(repo_path, "add", "a.txt", "b.txt")
    _run(repo_path, "commit", "-m", "Update a.txt, add b.txt")

    return repo_path
