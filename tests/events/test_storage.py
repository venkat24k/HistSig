from src.events.formation import CandidateEvent
from src.events.storage import insert_events


def _seed_contributor_github(conn, repo_id, login):
    conn.execute(
        "INSERT INTO contributors (repo_id, canonical_name, canonical_email, github_login, is_bot, identity_confidence, merged_identity_count) "
        "VALUES (?, ?, NULL, ?, 0, 'github_login', 1)",
        (repo_id, login, login),
    )
    contributor_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO contributor_github_identities (repo_id, github_login, contributor_id) VALUES (?, ?, ?)", (repo_id, login, contributor_id))
    conn.commit()
    return contributor_id


def _seed_contributor_git(conn, repo_id, name, email):
    conn.execute(
        "INSERT INTO contributors (repo_id, canonical_name, canonical_email, github_login, is_bot, identity_confidence, merged_identity_count) "
        "VALUES (?, ?, ?, NULL, 0, 'name_email_pair', 1)",
        (repo_id, name, email),
    )
    contributor_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO contributor_git_identities (repo_id, author_name, author_email, contributor_id) VALUES (?, ?, ?, ?)", (repo_id, name, email, contributor_id))
    conn.commit()
    return contributor_id


def test_insert_events_resolves_author_by_github_login(processed_conn):
    expected_id = _seed_contributor_github(processed_conn, repo_id=1, login="bob")
    event = CandidateEvent(
        granularity="pr_bundle", event_type="pull_request", source_pr_number=1, primary_commit_hash=None,
        title="t", author_login="bob", author_git_identity=None, occurred_at="2024-01-01", commit_hashes=["c1"],
    )

    summary = insert_events(processed_conn, repo_id=1, granularity="pr_bundle", events=[event])

    assert summary["unresolved_authors"] == 0
    row = processed_conn.execute("SELECT author_contributor_id FROM candidate_events").fetchone()
    assert row[0] == expected_id


def test_insert_events_resolves_author_by_git_identity(processed_conn):
    expected_id = _seed_contributor_git(processed_conn, repo_id=1, name="Alice", email="alice@example.com")
    event = CandidateEvent(
        granularity="pr_bundle", event_type="standalone_commit", source_pr_number=None, primary_commit_hash="c1",
        title="t", author_login=None, author_git_identity=("Alice", "alice@example.com"),
        occurred_at="2024-01-01", commit_hashes=["c1"],
    )

    insert_events(processed_conn, repo_id=1, granularity="pr_bundle", events=[event])

    row = processed_conn.execute("SELECT author_contributor_id FROM candidate_events").fetchone()
    assert row[0] == expected_id


def test_insert_events_handles_unresolvable_author(processed_conn):
    event = CandidateEvent(
        granularity="pr_bundle", event_type="standalone_commit", source_pr_number=None, primary_commit_hash="c1",
        title="t", author_login=None, author_git_identity=("Nobody", "nobody@example.com"),
        occurred_at="2024-01-01", commit_hashes=["c1"],
    )

    summary = insert_events(processed_conn, repo_id=1, granularity="pr_bundle", events=[event])

    assert summary["unresolved_authors"] == 1
    row = processed_conn.execute("SELECT author_contributor_id FROM candidate_events").fetchone()
    assert row[0] is None


def test_insert_events_links_event_commits(processed_conn):
    event = CandidateEvent(
        granularity="pr_bundle", event_type="pull_request", source_pr_number=1, primary_commit_hash=None,
        title="t", author_login=None, author_git_identity=None, occurred_at="2024-01-01", commit_hashes=["c1", "c2"],
    )

    insert_events(processed_conn, repo_id=1, granularity="pr_bundle", events=[event])

    event_id = processed_conn.execute("SELECT id FROM candidate_events").fetchone()[0]
    hashes = {r[0] for r in processed_conn.execute("SELECT commit_hash FROM event_commits WHERE event_id=?", (event_id,))}
    assert hashes == {"c1", "c2"}


def test_insert_events_is_idempotent_per_granularity(processed_conn):
    event = CandidateEvent(
        granularity="pr_bundle", event_type="pull_request", source_pr_number=1, primary_commit_hash=None,
        title="t", author_login=None, author_git_identity=None, occurred_at="2024-01-01", commit_hashes=["c1"],
    )
    insert_events(processed_conn, repo_id=1, granularity="pr_bundle", events=[event])
    insert_events(processed_conn, repo_id=1, granularity="pr_bundle", events=[event])

    assert processed_conn.execute("SELECT COUNT(*) FROM candidate_events").fetchone()[0] == 1
    assert processed_conn.execute("SELECT COUNT(*) FROM event_commits").fetchone()[0] == 1


def test_insert_events_does_not_clobber_other_granularity(processed_conn):
    pr_event = CandidateEvent(
        granularity="pr_bundle", event_type="pull_request", source_pr_number=1, primary_commit_hash=None,
        title="t", author_login=None, author_git_identity=None, occurred_at="2024-01-01", commit_hashes=["c1"],
    )
    commit_event = CandidateEvent(
        granularity="commit_level", event_type="commit", source_pr_number=None, primary_commit_hash="c1",
        title="t", author_login=None, author_git_identity=None, occurred_at="2024-01-01", commit_hashes=["c1"],
    )
    insert_events(processed_conn, repo_id=1, granularity="pr_bundle", events=[pr_event])
    insert_events(processed_conn, repo_id=1, granularity="commit_level", events=[commit_event])

    assert processed_conn.execute("SELECT COUNT(*) FROM candidate_events").fetchone()[0] == 2
    # re-running just one granularity leaves the other untouched
    insert_events(processed_conn, repo_id=1, granularity="pr_bundle", events=[pr_event])
    assert processed_conn.execute("SELECT COUNT(*) FROM candidate_events").fetchone()[0] == 2
