from src.events.orchestrate import form_and_store_events
from tests.events.test_storage import _seed_contributor_git, _seed_contributor_github


def test_form_and_store_events_end_to_end(raw_conn, processed_conn):
    _seed_contributor_github(processed_conn, repo_id=1, login="bob")
    _seed_contributor_git(processed_conn, repo_id=1, name="Alice", email="alice@example.com")

    raw_conn.execute(
        "INSERT INTO pull_requests (id, repo_id, number, title, author_login, state, created_at, merged_at, "
        "reviews_truncated, commits_truncated, review_comments_truncated) "
        "VALUES (1, 1, 100, 'Add feature', 'bob', 'closed', '2024-01-01T00:00:00Z', '2024-01-02T00:00:00Z', 0, 0, 0)"
    )
    raw_conn.execute(
        "INSERT INTO commits (repo_id, hash, author_name, author_email, author_date_utc, message, is_merge, "
        "parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, 'c1', 'Alice', 'alice@example.com', '2024-01-01T00:00:00Z', 'part of PR', 0, '', 0, 0, 0)"
    )
    raw_conn.execute(
        "INSERT INTO commits (repo_id, hash, author_name, author_email, author_date_utc, message, is_merge, "
        "parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, 'c2', 'Alice', 'alice@example.com', '2024-01-03T00:00:00Z', 'direct push', 0, '', 0, 0, 0)"
    )
    raw_conn.execute("INSERT INTO pr_commits (pr_id, commit_hash) VALUES (1, 'c1')")
    raw_conn.commit()

    results = form_and_store_events(raw_conn, processed_conn, repo_id=1)

    assert results["pr_bundle"]["events_created"] == 2  # 1 PR + 1 standalone commit
    assert results["pr_bundle"]["unresolved_authors"] == 0
    assert results["commit_level"]["events_created"] == 2  # both commits, individually

    pr_events = processed_conn.execute("SELECT event_type FROM candidate_events WHERE granularity='pr_bundle'").fetchall()
    assert {r[0] for r in pr_events} == {"pull_request", "standalone_commit"}

    commit_level_events = processed_conn.execute("SELECT event_type FROM candidate_events WHERE granularity='commit_level'").fetchall()
    assert len(commit_level_events) == 2
    assert all(r[0] == "commit" for r in commit_level_events)
