import pytest

from src.api import repositories
from src.collection.schema import connect as connect_raw
from src.events.schema import create_schema as create_events_schema
from src.processing.schema import connect as connect_processed


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    (tmp_path / "raw").mkdir()
    (tmp_path / "processed").mkdir()
    monkeypatch.setattr(repositories, "DATA_DIR", tmp_path)
    return tmp_path


def seed_repo(data_dir, safe_name, url="https://github.com/o/r", name="o/r", with_processed=True, with_events=True):
    raw_conn = connect_raw(str(data_dir / "raw" / f"{safe_name}.db"))
    raw_conn.execute("INSERT INTO repositories (url, name, default_branch, collected_at) VALUES (?, ?, 'main', '2024-01-01')", (url, name))
    repo_id = raw_conn.execute("SELECT id FROM repositories WHERE url = ?", (url,)).fetchone()[0]
    raw_conn.execute(
        "INSERT INTO commits (repo_id, hash, author_name, author_email, message, is_merge, parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (?, 'c1', 'Alice', 'alice@example.com', 'Initial commit', 0, '', 1, 0, 1)",
        (repo_id,),
    )
    raw_conn.execute(
        "INSERT INTO pull_requests (id, repo_id, number, title, body, state, author_login, created_at, merged_at, base_branch, head_branch, "
        "reviews_truncated, commits_truncated, review_comments_truncated) "
        "VALUES (1, ?, 10, 'Add feature', 'desc', 'closed', 'bob', '2024-01-01T00:00:00Z', '2024-01-02T00:00:00Z', 'main', 'feature', 0, 0, 0)",
        (repo_id,),
    )
    raw_conn.commit()

    if not with_processed:
        return repo_id

    processed_conn = connect_processed(str(data_dir / "processed" / f"{safe_name}.db"))
    processed_conn.execute(
        "INSERT INTO contributors (repo_id, canonical_name, canonical_email, github_login, is_bot, identity_confidence, merged_identity_count) "
        "VALUES (?, 'Bob', NULL, 'bob', 0, 'github_login', 1)",
        (repo_id,),
    )
    contributor_id = processed_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    processed_conn.commit()

    if not with_events:
        return repo_id

    create_events_schema(processed_conn)
    processed_conn.execute(
        "INSERT INTO candidate_events (repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, author_contributor_id, occurred_at) "
        "VALUES (?, 'pr_bundle', 'pull_request', 10, NULL, 'Add feature', ?, '2024-01-02T00:00:00Z')",
        (repo_id, contributor_id),
    )
    event_id = processed_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    processed_conn.execute("INSERT INTO event_commits (event_id, commit_hash) VALUES (?, 'c1')", (event_id,))
    processed_conn.commit()
    return repo_id
