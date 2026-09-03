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


@pytest.fixture
def tmp_git_repo_with_nested_rename(tmp_path):
    """Two same-named files in different directories, one later renamed
    across directories — regression coverage for the basename-vs-full-path
    bug (mf.filename is only a basename in PyDriller, which collides across
    directories and doesn't match old_path's full-path form)."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _run(repo_path, "init", "-b", "main")
    _run(repo_path, "config", "user.name", "Test Author")
    _run(repo_path, "config", "user.email", "author@example.com")

    (repo_path / "pkg_a").mkdir()
    (repo_path / "pkg_b").mkdir()
    (repo_path / "pkg_a" / "__init__.py").write_text("a\n")
    (repo_path / "pkg_b" / "__init__.py").write_text("b\n")
    _run(repo_path, "add", ".")
    _run(repo_path, "commit", "-m", "Add pkg_a and pkg_b, both with __init__.py")

    _run(repo_path, "mv", "pkg_a/__init__.py", "pkg_a/core.py")
    _run(repo_path, "commit", "-m", "Rename pkg_a/__init__.py to pkg_a/core.py")

    return repo_path
