from src.events.formation import (
    form_commit_level_events,
    form_events,
    form_pr_bundle_events,
    form_standalone_commit_events,
)


def _insert_commit(conn, hash_, name="Alice", email="alice@example.com", message="msg", date="2024-01-01T00:00:00+00:00"):
    conn.execute(
        "INSERT INTO commits (repo_id, hash, author_name, author_email, author_date_utc, message, is_merge, parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, ?, ?, ?, ?, ?, 0, '', 0, 0, 0)",
        (hash_, name, email, date, message),
    )


def _insert_pr(conn, pr_id, number, title="PR title", author_login="bob", created_at="2024-01-01T00:00:00Z", merged_at=None, closed_at=None):
    conn.execute(
        "INSERT INTO pull_requests (id, repo_id, number, title, author_login, state, created_at, merged_at, closed_at, "
        "reviews_truncated, commits_truncated, review_comments_truncated) VALUES (?, 1, ?, ?, ?, 'open', ?, ?, ?, 0, 0, 0)",
        (pr_id, number, title, author_login, created_at, merged_at, closed_at),
    )


def _link_pr_commit(conn, pr_id, commit_hash):
    conn.execute("INSERT INTO pr_commits (pr_id, commit_hash) VALUES (?, ?)", (pr_id, commit_hash))


def test_pr_bundle_events_group_commits_under_the_pr(raw_conn):
    _insert_pr(raw_conn, 1, 100, title="Add feature", author_login="bob", merged_at="2024-02-01T00:00:00Z")
    _insert_commit(raw_conn, "c1")
    _insert_commit(raw_conn, "c2")
    _link_pr_commit(raw_conn, 1, "c1")
    _link_pr_commit(raw_conn, 1, "c2")
    raw_conn.commit()

    events = form_pr_bundle_events(raw_conn)

    assert len(events) == 1
    assert events[0].event_type == "pull_request"
    assert events[0].source_pr_number == 100
    assert sorted(events[0].commit_hashes) == ["c1", "c2"]
    assert events[0].occurred_at == "2024-02-01T00:00:00Z"


def test_pr_occurred_at_prefers_merged_then_closed_then_created(raw_conn):
    _insert_pr(raw_conn, 1, 1, created_at="2024-01-01T00:00:00Z", merged_at=None, closed_at=None)
    _insert_pr(raw_conn, 2, 2, created_at="2024-01-01T00:00:00Z", merged_at=None, closed_at="2024-01-02T00:00:00Z")
    _insert_pr(raw_conn, 3, 3, created_at="2024-01-01T00:00:00Z", merged_at="2024-01-03T00:00:00Z", closed_at="2024-01-02T00:00:00Z")
    raw_conn.commit()

    events = {e.source_pr_number: e for e in form_pr_bundle_events(raw_conn)}
    assert events[1].occurred_at == "2024-01-01T00:00:00Z"  # created only
    assert events[2].occurred_at == "2024-01-02T00:00:00Z"  # closed, not merged
    assert events[3].occurred_at == "2024-01-03T00:00:00Z"  # merged wins


def test_standalone_commit_events_exclude_pr_commits(raw_conn):
    _insert_pr(raw_conn, 1, 100)
    _insert_commit(raw_conn, "in_pr")
    _insert_commit(raw_conn, "direct_push", message="Fix typo directly on main")
    _link_pr_commit(raw_conn, 1, "in_pr")
    raw_conn.commit()

    events = form_standalone_commit_events(raw_conn)

    assert len(events) == 1
    assert events[0].primary_commit_hash == "direct_push"
    assert events[0].event_type == "standalone_commit"
    assert events[0].title == "Fix typo directly on main"


def test_commit_level_events_include_every_commit_regardless_of_pr_membership(raw_conn):
    _insert_pr(raw_conn, 1, 100)
    _insert_commit(raw_conn, "in_pr")
    _insert_commit(raw_conn, "direct_push")
    _link_pr_commit(raw_conn, 1, "in_pr")
    raw_conn.commit()

    events = form_commit_level_events(raw_conn)

    assert len(events) == 2
    assert {e.primary_commit_hash for e in events} == {"in_pr", "direct_push"}
    assert all(e.event_type == "commit" for e in events)


def test_pr_bundle_granularity_combines_prs_and_standalone_commits(raw_conn):
    _insert_pr(raw_conn, 1, 100, merged_at="2024-02-01T00:00:00Z")
    _insert_commit(raw_conn, "in_pr")
    _insert_commit(raw_conn, "direct_push")
    _link_pr_commit(raw_conn, 1, "in_pr")
    raw_conn.commit()

    events = form_events(raw_conn, "pr_bundle")

    assert len(events) == 2
    types = {e.event_type for e in events}
    assert types == {"pull_request", "standalone_commit"}


def test_form_events_rejects_unknown_granularity(raw_conn):
    import pytest
    with pytest.raises(ValueError, match="pr_bundle"):
        form_events(raw_conn, "nonsense")
