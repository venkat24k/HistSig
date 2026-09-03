from src.collection.git_collector import collect_git_history, ensure_local_clone


def test_collect_git_history_returns_one_record_per_commit(tmp_git_repo):
    commits = collect_git_history(str(tmp_git_repo))

    assert len(commits) == 2
    assert [c.message.strip() for c in commits] == ["Add a.txt", "Update a.txt, add b.txt"]


def test_collect_git_history_captures_author_identity(tmp_git_repo):
    commits = collect_git_history(str(tmp_git_repo))

    for commit in commits:
        assert commit.author_name == "Test Author"
        assert commit.author_email == "author@example.com"
        assert commit.author_date is not None
        assert commit.author_date_utc is not None


def test_collect_git_history_utc_dates_sort_correctly_across_offsets(tmp_git_repo):
    """Regression test: author_date keeps each commit's original local UTC
    offset, which does NOT sort correctly as plain text against a
    different offset (e.g. "10:00-03:00" is textually before "09:00+02:00"
    even though the second happened three hours earlier in absolute time).
    author_date_utc must always sort correctly regardless of offset."""
    import datetime

    commits = collect_git_history(str(tmp_git_repo))
    for commit in commits:
        parsed_utc = datetime.datetime.fromisoformat(commit.author_date_utc)
        assert parsed_utc.utcoffset() == datetime.timedelta(0)
        parsed_original = datetime.datetime.fromisoformat(commit.author_date)
        assert parsed_utc == parsed_original  # same instant, normalized offset


def test_collect_git_history_captures_changed_files(tmp_git_repo):
    commits = collect_git_history(str(tmp_git_repo))
    first_commit, second_commit = commits

    assert [f.filename for f in first_commit.files] == ["a.txt"]
    assert first_commit.files[0].change_type == "ADD"

    second_commit_filenames = {f.filename for f in second_commit.files}
    assert second_commit_filenames == {"a.txt", "b.txt"}
    change_types = {f.filename: f.change_type for f in second_commit.files}
    assert change_types["a.txt"] == "MODIFY"
    assert change_types["b.txt"] == "ADD"


def test_collect_git_history_uses_full_paths_not_basenames(tmp_git_repo_with_nested_rename):
    """Regression test: PyDriller's mf.filename is only a basename, which
    would make pkg_a/__init__.py and pkg_b/__init__.py indistinguishable
    and wouldn't line up with old_path (a full path) for rename tracking."""
    commits = collect_git_history(str(tmp_git_repo_with_nested_rename))
    add_commit, rename_commit = commits

    add_paths = {f.filename for f in add_commit.files}
    assert add_paths == {"pkg_a/__init__.py", "pkg_b/__init__.py"}

    rename_file = rename_commit.files[0]
    assert rename_file.change_type == "RENAME"
    assert rename_file.old_path == "pkg_a/__init__.py"
    assert rename_file.filename == "pkg_a/core.py"


def test_collect_git_history_is_not_merge_for_linear_history(tmp_git_repo):
    commits = collect_git_history(str(tmp_git_repo))

    assert all(not c.is_merge for c in commits)
    assert commits[1].parent_hashes == [commits[0].hash]


def test_ensure_local_clone_clones_when_missing(tmp_git_repo, tmp_path):
    # tmp_git_repo stands in for a "remote" here — cloning from a local path
    # exercises the same git subprocess path as a real remote URL, fully offline.
    clone_dir = tmp_path / "mirror"

    result_path = ensure_local_clone(str(tmp_git_repo), str(clone_dir))

    assert result_path == str(clone_dir)
    assert (clone_dir / ".git").exists()
    assert collect_git_history(result_path) == collect_git_history(str(tmp_git_repo))


def test_ensure_local_clone_fetches_and_updates_local_branch_when_already_present(tmp_git_repo, tmp_path):
    """A second call must pick up commits made on the "remote" since the
    first clone — plain `git fetch` alone would update only the
    remote-tracking ref, leaving the checked-out branch (and therefore what
    PyDriller walks) stale; ensure_local_clone resets it to match."""
    clone_dir = tmp_path / "mirror"
    ensure_local_clone(str(tmp_git_repo), str(clone_dir))
    initial_commit_count = len(collect_git_history(str(clone_dir)))

    (tmp_git_repo / "c.txt").write_text("third file\n")
    import subprocess
    subprocess.run(["git", "-C", str(tmp_git_repo), "add", "c.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_git_repo), "commit", "-m", "Add c.txt"], check=True)

    ensure_local_clone(str(tmp_git_repo), str(clone_dir))

    updated_commits = collect_git_history(str(clone_dir))
    assert len(updated_commits) == initial_commit_count + 1
    assert updated_commits[-1].message.strip() == "Add c.txt"


def test_collect_git_history_rejects_remote_looking_urls():
    import pytest
    with pytest.raises(ValueError, match="local path"):
        collect_git_history("https://github.com/pallets/click")
    with pytest.raises(ValueError, match="local path"):
        collect_git_history("git@github.com:pallets/click.git")
