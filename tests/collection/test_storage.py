import sqlite3

from src.collection.git_collector import CommitRecord, FileChangeRecord
from src.collection.github_collector import (
    IssueCommentRecord,
    IssueRecord,
    PRReviewCommentRecord,
    PRReviewRecord,
    PullRequestRecord,
    ReleaseRecord,
)
from src.collection.schema import create_schema
from src.collection.storage import (
    insert_commits,
    insert_issues,
    insert_pull_requests,
    insert_releases,
    upsert_repository,
)


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def test_upsert_repository_returns_same_id_on_repeat_call():
    conn = make_conn()

    first_id = upsert_repository(conn, url="https://example.com/repo.git", name="repo")
    second_id = upsert_repository(conn, url="https://example.com/repo.git", name="repo")

    assert first_id == second_id
    count = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
    assert count == 1


def _sample_commit(message="Initial commit"):
    return CommitRecord(
        hash="abc123",
        author_name="Test Author",
        author_email="author@example.com",
        author_date="2024-01-01T00:00:00+00:00",
        committer_name="Test Author",
        committer_email="author@example.com",
        committer_date="2024-01-01T00:00:00+00:00",
        message=message,
        is_merge=False,
        parent_hashes=[],
        insertions=1,
        deletions=0,
        files_changed_count=1,
        files=[FileChangeRecord(filename="a.txt", old_path=None, change_type="ADD", insertions=1, deletions=0)],
    )


def test_insert_commits_is_idempotent_on_repeat_insert():
    conn = make_conn()
    repo_id = upsert_repository(conn, url="https://example.com/repo.git", name="repo")

    insert_commits(conn, repo_id, [_sample_commit()])
    insert_commits(conn, repo_id, [_sample_commit()])

    commit_count = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    file_count = conn.execute("SELECT COUNT(*) FROM commit_files").fetchone()[0]
    assert commit_count == 1
    assert file_count == 1


def test_insert_commits_updates_fields_on_re_collection():
    conn = make_conn()
    repo_id = upsert_repository(conn, url="https://example.com/repo.git", name="repo")

    insert_commits(conn, repo_id, [_sample_commit(message="Original message")])
    insert_commits(conn, repo_id, [_sample_commit(message="Amended message")])

    stored_message = conn.execute("SELECT message FROM commits WHERE hash = 'abc123'").fetchone()[0]
    assert stored_message == "Amended message"


def _sample_issue(title="Bug report"):
    return IssueRecord(
        id=1, number=10, title=title, body="it broke", state="open",
        author_login="alice", created_at="2024-01-01T00:00:00+00:00", closed_at=None, updated_at=None,
        labels=["bug", "priority-high"],
        comments=[IssueCommentRecord(id=1, author_login="bob", created_at="2024-01-02T00:00:00+00:00", body="me too")],
    )


def test_insert_issues_is_idempotent_and_updates_labels():
    conn = make_conn()
    repo_id = upsert_repository(conn, url="https://example.com/repo.git", name="repo")

    insert_issues(conn, repo_id, [_sample_issue()])
    insert_issues(conn, repo_id, [_sample_issue(title="Bug report (updated)")])

    assert conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 1
    assert conn.execute("SELECT title FROM issues WHERE id = 1").fetchone()[0] == "Bug report (updated)"
    assert conn.execute("SELECT COUNT(*) FROM issue_labels WHERE issue_id = 1").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM issue_comments WHERE issue_id = 1").fetchone()[0] == 1


def _sample_pr(title="Add feature"):
    return PullRequestRecord(
        id=1, number=5, title=title, body="desc", state="closed",
        author_login="dave", created_at="2024-01-01T00:00:00+00:00", merged_at="2024-01-03T00:00:00+00:00",
        closed_at="2024-01-03T00:00:00+00:00", updated_at=None,
        base_branch="main", head_branch="feature-branch", merge_commit_sha="cafebabe",
        labels=["enhancement"], commit_shas=["deadbeef", "beadfeed"],
        reviews=[PRReviewRecord(id=1, reviewer_login="reviewer1", state="APPROVED", submitted_at=None, body="lgtm")],
        review_comments=[
            PRReviewCommentRecord(id=1, review_id=1, author_login="reviewer1",
                                   created_at=None, body="nit", path="src/foo.py")
        ],
    )


def test_insert_pull_requests_is_idempotent_across_all_child_tables():
    conn = make_conn()
    repo_id = upsert_repository(conn, url="https://example.com/repo.git", name="repo")

    insert_pull_requests(conn, repo_id, [_sample_pr()])
    insert_pull_requests(conn, repo_id, [_sample_pr(title="Add feature (updated)")])

    assert conn.execute("SELECT COUNT(*) FROM pull_requests").fetchone()[0] == 1
    assert conn.execute("SELECT title FROM pull_requests WHERE id = 1").fetchone()[0] == "Add feature (updated)"
    assert conn.execute("SELECT COUNT(*) FROM pr_labels WHERE pr_id = 1").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM pr_commits WHERE pr_id = 1").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM pr_reviews WHERE pr_id = 1").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM pr_review_comments WHERE pr_id = 1").fetchone()[0] == 1


def test_insert_releases_is_idempotent():
    conn = make_conn()
    repo_id = upsert_repository(conn, url="https://example.com/repo.git", name="repo")
    release = ReleaseRecord(
        id=1, tag_name="v1.0.0", name="First release",
        created_at="2024-01-01T00:00:00+00:00", published_at="2024-01-01T00:00:00+00:00",
        author_login="maintainer", body="notes",
    )

    insert_releases(conn, repo_id, [release])
    insert_releases(conn, repo_id, [release])

    assert conn.execute("SELECT COUNT(*) FROM releases").fetchone()[0] == 1
