from src.processing.normalize import normalize_repository
from src.processing.schema import connect


def _insert_commit(conn, hash_, name, email, message="msg", date="2024-01-01"):
    conn.execute(
        "INSERT INTO commits (repo_id, hash, author_name, author_email, author_date, author_date_utc, message, is_merge, parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, 0, '', 0, 0, 0)",
        (hash_, name, email, date, date, message),
    )


def test_normalize_repository_end_to_end(raw_conn, tmp_path):
    # A GitHub-linked committer (noreply email) who also opened an issue.
    raw_conn.execute("INSERT INTO issues (id, repo_id, number, title, author_login, comments_truncated) VALUES (1, 1, 1, 't', 'octocat', 0)")
    _insert_commit(raw_conn, "aaaa1111", "The Octocat", "octocat@users.noreply.github.com", "Add feature", "2024-01-01")

    # A revert of that commit by a git-only identity.
    _insert_commit(raw_conn, "bbbb2222", "Alice", "alice@example.com",
                    "Revert \"Add feature\"\n\nThis reverts commit aaaa1111.\n", "2024-01-02")

    # A file added then renamed, tying the two commits together.
    raw_conn.execute("INSERT INTO commit_files (repo_id, commit_hash, filename, old_path, change_type, insertions, deletions) VALUES (1, 'aaaa1111', 'a.py', NULL, 'ADD', 1, 0)")
    raw_conn.execute("INSERT INTO commit_files (repo_id, commit_hash, filename, old_path, change_type, insertions, deletions) VALUES (1, 'bbbb2222', 'b.py', 'a.py', 'RENAME', 0, 0)")
    raw_conn.commit()

    processed_conn = connect(str(tmp_path / "processed.db"))
    summary = normalize_repository(raw_conn, processed_conn, repo_id=1)

    assert summary["contributors"] == 2
    assert summary["commits_annotated"] == 2
    assert summary["commits_unresolved_identity"] == 0
    assert summary["reverts_detected"] == 1
    assert summary["file_identities"] == 1
    assert summary["renamed_files"] == 1
    assert summary["has_issues"] is True
    assert summary["has_releases"] is False

    # The octocat commit's contributor should be the same row as the issue's.
    row = processed_conn.execute(
        """
        SELECT c.github_login FROM commit_annotations ca
        JOIN contributors c ON ca.contributor_id = c.id
        WHERE ca.commit_hash = 'aaaa1111'
        """
    ).fetchone()
    assert row[0] == "octocat"

    revert_row = processed_conn.execute(
        "SELECT is_revert, reverts_commit_hash FROM commit_annotations WHERE commit_hash = 'bbbb2222'"
    ).fetchone()
    assert revert_row == (1, "aaaa1111")


def test_normalize_repository_is_safe_to_rerun(raw_conn, tmp_path):
    # Regression test: re-running normalize against a repo that already
    # has processed data used to raise sqlite3.IntegrityError, because
    # insert_contributors deleted `contributors` while the previous run's
    # commit_annotations rows still referenced those ids via
    # commit_annotations.contributor_id -- a real bug that would crash
    # every "analyze this repository again" (e.g. to pick up new commits)
    # after the first run, not just a hypothetical.
    _insert_commit(raw_conn, "aaaa1111", "The Octocat", "octocat@users.noreply.github.com")
    raw_conn.commit()

    processed_conn = connect(str(tmp_path / "processed.db"))
    normalize_repository(raw_conn, processed_conn, repo_id=1)
    summary = normalize_repository(raw_conn, processed_conn, repo_id=1)

    assert summary["contributors"] == 1
    assert processed_conn.execute("SELECT COUNT(*) FROM contributors").fetchone()[0] == 1
    assert processed_conn.execute("SELECT COUNT(*) FROM commit_annotations").fetchone()[0] == 1
