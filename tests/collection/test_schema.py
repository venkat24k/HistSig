import sqlite3

from src.collection.schema import create_schema

EXPECTED_TABLES = {
    "repositories", "commits", "commit_files",
    "issues", "issue_labels", "issue_comments",
    "pull_requests", "pr_commits", "pr_labels", "pr_reviews", "pr_review_comments",
    "releases",
}


def test_create_schema_creates_all_tables():
    conn = sqlite3.connect(":memory:")
    create_schema(conn)

    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {r[0] for r in rows}

    assert EXPECTED_TABLES.issubset(table_names)


def test_create_schema_is_idempotent():
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    create_schema(conn)  # must not raise
