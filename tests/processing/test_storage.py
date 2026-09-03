from src.processing.commits import RevertInfo
from src.processing.files import FileIdentityRecord, FilePathObservation
from src.processing.identity import ContributorRecord
from src.processing.schema import connect
from src.processing.storage import (
    insert_commit_annotations,
    insert_contributors,
    insert_data_availability,
    insert_file_identities,
)


def make_conn(tmp_path):
    return connect(str(tmp_path / "processed.db"))


def test_insert_contributors_replaces_on_rerun(tmp_path):
    conn = make_conn(tmp_path)
    first = [ContributorRecord(canonical_name="Alice", canonical_email="a@x.com", github_login=None, is_bot=False, identity_confidence="name_email_pair", git_identities=[("Alice", "a@x.com")])]
    insert_contributors(conn, repo_id=1, contributors=first)
    assert conn.execute("SELECT COUNT(*) FROM contributors").fetchone()[0] == 1

    second = [
        ContributorRecord(canonical_name="Alice", canonical_email="a@x.com", github_login=None, is_bot=False, identity_confidence="name_email_pair", git_identities=[("Alice", "a@x.com")]),
        ContributorRecord(canonical_name="Bob", canonical_email="b@x.com", github_login=None, is_bot=False, identity_confidence="name_email_pair", git_identities=[("Bob", "b@x.com")]),
    ]
    insert_contributors(conn, repo_id=1, contributors=second)

    assert conn.execute("SELECT COUNT(*) FROM contributors").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM contributor_git_identities").fetchone()[0] == 2


def test_insert_commit_annotations_replaces_on_rerun(tmp_path):
    conn = make_conn(tmp_path)
    insert_commit_annotations(conn, repo_id=1, annotations=[("h1", None, RevertInfo(False, None))])
    assert conn.execute("SELECT COUNT(*) FROM commit_annotations").fetchone()[0] == 1

    insert_commit_annotations(conn, repo_id=1, annotations=[
        ("h1", None, RevertInfo(True, "h0")),
        ("h2", None, RevertInfo(False, None)),
    ])
    rows = conn.execute("SELECT commit_hash, is_revert, reverts_commit_hash FROM commit_annotations ORDER BY commit_hash").fetchall()
    assert rows == [("h1", 1, "h0"), ("h2", 0, None)]


def test_insert_file_identities_replaces_on_rerun(tmp_path):
    conn = make_conn(tmp_path)
    files = [FileIdentityRecord(first_path="a.py", last_path="b.py", is_deleted=False, path_history=[
        FilePathObservation("h1", "a.py", "ADD"), FilePathObservation("h2", "b.py", "RENAME"),
    ])]
    insert_file_identities(conn, repo_id=1, files=files)

    assert conn.execute("SELECT COUNT(*) FROM file_identities").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM file_path_history").fetchone()[0] == 2

    insert_file_identities(conn, repo_id=1, files=files)
    assert conn.execute("SELECT COUNT(*) FROM file_identities").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM file_path_history").fetchone()[0] == 2


def test_insert_data_availability_is_idempotent(tmp_path):
    conn = make_conn(tmp_path)
    insert_data_availability(conn, repo_id=1, has_releases=True, has_pr_reviews=False, has_issues=True,
                              earliest_commit_date="2020-01-01", latest_commit_date="2024-01-01")
    insert_data_availability(conn, repo_id=1, has_releases=False, has_pr_reviews=False, has_issues=True,
                              earliest_commit_date="2020-01-01", latest_commit_date="2025-01-01")

    row = conn.execute("SELECT has_releases, latest_commit_date FROM repository_data_availability WHERE repo_id=1").fetchone()
    assert row == (0, "2025-01-01")
    assert conn.execute("SELECT COUNT(*) FROM repository_data_availability").fetchone()[0] == 1
