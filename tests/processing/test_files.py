from src.processing.files import build_file_identities


def _insert_commit(conn, hash_, date):
    conn.execute(
        "INSERT INTO commits (repo_id, hash, author_date, author_date_utc, message, is_merge, parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, ?, ?, ?, 'msg', 0, '', 0, 0, 0)",
        (hash_, date, date),
    )


def _insert_file_change(conn, hash_, filename, old_path, change_type):
    conn.execute(
        "INSERT INTO commit_files (repo_id, commit_hash, filename, old_path, change_type, insertions, deletions) VALUES (1, ?, ?, ?, ?, 0, 0)",
        (hash_, filename, old_path, change_type),
    )


def test_add_then_modify_is_one_identity(raw_conn):
    _insert_commit(raw_conn, "h1", "2024-01-01")
    _insert_file_change(raw_conn, "h1", "a.py", None, "ADD")
    _insert_commit(raw_conn, "h2", "2024-01-02")
    _insert_file_change(raw_conn, "h2", "a.py", None, "MODIFY")
    raw_conn.commit()

    files = build_file_identities(raw_conn)

    assert len(files) == 1
    assert files[0].first_path == files[0].last_path == "a.py"
    assert len(files[0].path_history) == 2
    assert files[0].is_deleted is False


def test_rename_chain_preserves_one_identity(raw_conn):
    _insert_commit(raw_conn, "h1", "2024-01-01")
    _insert_file_change(raw_conn, "h1", "a.py", None, "ADD")
    _insert_commit(raw_conn, "h2", "2024-01-02")
    _insert_file_change(raw_conn, "h2", "b.py", "a.py", "RENAME")
    _insert_commit(raw_conn, "h3", "2024-01-03")
    _insert_file_change(raw_conn, "h3", "c.py", "b.py", "RENAME")
    raw_conn.commit()

    files = build_file_identities(raw_conn)

    assert len(files) == 1
    assert files[0].first_path == "a.py"
    assert files[0].last_path == "c.py"
    assert [obs.path for obs in files[0].path_history] == ["a.py", "b.py", "c.py"]


def test_delete_then_new_add_at_same_path_is_a_new_identity(raw_conn):
    _insert_commit(raw_conn, "h1", "2024-01-01")
    _insert_file_change(raw_conn, "h1", "a.py", None, "ADD")
    _insert_commit(raw_conn, "h2", "2024-01-02")
    _insert_file_change(raw_conn, "h2", "a.py", None, "DELETE")
    _insert_commit(raw_conn, "h3", "2024-01-03")
    _insert_file_change(raw_conn, "h3", "a.py", None, "ADD")
    raw_conn.commit()

    files = build_file_identities(raw_conn)

    assert len(files) == 2
    assert files[0].is_deleted is True
    assert files[1].is_deleted is False


def test_delete_then_add_at_same_path_in_same_commit_is_two_identities(raw_conn):
    # Real-world case (seen in Homebrew/BrewUI's history): a single commit
    # both deletes and re-adds the same path, e.g. a submodule/symlink
    # replaced by a regular file. change_type ordering follows commit_files
    # insertion order (cf.id), so DELETE is processed before ADD here.
    _insert_commit(raw_conn, "h1", "2024-01-01")
    _insert_file_change(raw_conn, "h1", "a.py", None, "ADD")
    _insert_commit(raw_conn, "h2", "2024-01-02")
    _insert_file_change(raw_conn, "h2", "a.py", None, "DELETE")
    _insert_file_change(raw_conn, "h2", "a.py", None, "ADD")
    raw_conn.commit()

    files = build_file_identities(raw_conn)

    assert len(files) == 2
    assert files[0].is_deleted is True
    assert files[1].is_deleted is False
    # Both identities recorded an observation for the same (commit, path).
    assert [obs.path for obs in files[0].path_history] == ["a.py", "a.py"]
    assert [obs.change_type for obs in files[0].path_history] == ["ADD", "DELETE"]
    assert [obs.path for obs in files[1].path_history] == ["a.py"]
    assert files[1].path_history[0].change_type == "ADD"


def test_same_basename_different_directories_are_different_identities(raw_conn):
    _insert_commit(raw_conn, "h1", "2024-01-01")
    _insert_file_change(raw_conn, "h1", "pkg_a/__init__.py", None, "ADD")
    _insert_file_change(raw_conn, "h1", "pkg_b/__init__.py", None, "ADD")
    raw_conn.commit()

    files = build_file_identities(raw_conn)

    assert len(files) == 2
    assert {f.first_path for f in files} == {"pkg_a/__init__.py", "pkg_b/__init__.py"}


def test_commits_processed_in_author_date_order_regardless_of_insertion_order(raw_conn):
    # Insert the later commit first to make sure ordering comes from author_date, not row id.
    _insert_commit(raw_conn, "h2", "2024-02-01")
    _insert_file_change(raw_conn, "h2", "b.py", "a.py", "RENAME")
    _insert_commit(raw_conn, "h1", "2024-01-01")
    _insert_file_change(raw_conn, "h1", "a.py", None, "ADD")
    raw_conn.commit()

    files = build_file_identities(raw_conn)

    assert len(files) == 1
    assert [obs.commit_hash for obs in files[0].path_history] == ["h1", "h2"]


def test_ordering_uses_utc_not_raw_offset_text(raw_conn):
    """Regression test: two commits whose *raw* author_date strings would
    sort in the wrong order as plain text (different UTC offsets) must
    still be walked in true chronological order via author_date_utc."""
    # h1 "happens" at 09:00 UTC (as 11:00+02:00); h2 at 13:00 UTC (as 10:00-03:00).
    # As raw text, "10:00-03:00" < "11:00+02:00", which would be backwards.
    raw_conn.execute(
        "INSERT INTO commits (repo_id, hash, author_date, author_date_utc, message, is_merge, parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, 'h1', '2024-01-01T11:00:00+02:00', '2024-01-01T09:00:00+00:00', 'msg', 0, '', 0, 0, 0)"
    )
    raw_conn.execute(
        "INSERT INTO commits (repo_id, hash, author_date, author_date_utc, message, is_merge, parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, 'h2', '2024-01-01T10:00:00-03:00', '2024-01-01T13:00:00+00:00', 'msg', 0, '', 0, 0, 0)"
    )
    _insert_file_change(raw_conn, "h1", "a.py", None, "ADD")
    _insert_file_change(raw_conn, "h2", "b.py", "a.py", "RENAME")
    raw_conn.commit()

    files = build_file_identities(raw_conn)

    assert len(files) == 1
    assert [obs.commit_hash for obs in files[0].path_history] == ["h1", "h2"]
