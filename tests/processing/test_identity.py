from src.processing.identity import is_bot_login, parse_noreply_login, resolve_contributors


def test_parse_noreply_login_with_numeric_prefix():
    assert parse_noreply_login("12345+octocat@users.noreply.github.com") == "octocat"


def test_parse_noreply_login_without_numeric_prefix():
    assert parse_noreply_login("octocat@users.noreply.github.com") == "octocat"


def test_parse_noreply_login_rejects_normal_email():
    assert parse_noreply_login("octocat@example.com") is None


def test_parse_noreply_login_handles_none():
    assert parse_noreply_login(None) is None


def test_is_bot_login():
    assert is_bot_login("dependabot[bot]") is True
    assert is_bot_login("octocat") is False
    assert is_bot_login(None) is False


def _insert_commit(conn, hash_, name, email):
    conn.execute(
        "INSERT INTO commits (repo_id, hash, author_name, author_email, message, is_merge, parent_hashes, insertions, deletions, files_changed_count) "
        "VALUES (1, ?, ?, ?, 'msg', 0, '', 0, 0, 0)",
        (hash_, name, email),
    )


def test_resolve_contributors_links_noreply_email_to_github_login(raw_conn):
    raw_conn.execute("INSERT INTO issues (id, repo_id, number, title, author_login, comments_truncated) VALUES (1, 1, 1, 't', 'octocat', 0)")
    _insert_commit(raw_conn, "h1", "The Octocat", "12345+octocat@users.noreply.github.com")
    raw_conn.commit()

    contributors = resolve_contributors(raw_conn)

    assert len(contributors) == 1
    c = contributors[0]
    assert c.github_login == "octocat"
    assert c.identity_confidence == "github_login"
    assert ("The Octocat", "12345+octocat@users.noreply.github.com") in c.git_identities
    assert c.merged_identity_count == 2  # 1 github login + 1 git identity


def test_resolve_contributors_clusters_by_email_when_no_github_link(raw_conn):
    _insert_commit(raw_conn, "h1", "Alice", "alice@example.com")
    _insert_commit(raw_conn, "h2", "Alice B.", "alice@example.com")  # same email, different display name
    raw_conn.commit()

    contributors = resolve_contributors(raw_conn)

    assert len(contributors) == 1
    assert contributors[0].identity_confidence == "name_email_pair"
    assert contributors[0].github_login is None
    assert len(contributors[0].git_identities) == 2


def test_resolve_contributors_does_not_merge_different_emails_even_with_same_name(raw_conn):
    """Conservative-by-design: same display name, different email ->
    different contributors, since fuzzy name matching risks false merges."""
    _insert_commit(raw_conn, "h1", "Alice", "alice@work.com")
    _insert_commit(raw_conn, "h2", "Alice", "alice@personal.com")
    raw_conn.commit()

    contributors = resolve_contributors(raw_conn)

    assert len(contributors) == 2


def test_resolve_contributors_flags_bot_from_github_login(raw_conn):
    raw_conn.execute("INSERT INTO pull_requests (id, repo_id, number, title, author_login, reviews_truncated, commits_truncated, review_comments_truncated) VALUES (1, 1, 1, 't', 'dependabot[bot]', 0, 0, 0)")
    raw_conn.commit()

    contributors = resolve_contributors(raw_conn)

    assert len(contributors) == 1
    assert contributors[0].is_bot is True


def test_resolve_contributors_github_only_identity_with_no_commits(raw_conn):
    """A reviewer/commenter who never authored a commit in this dataset
    still gets a contributor record, just with no git_identities."""
    raw_conn.execute("INSERT INTO pr_reviews (id, pr_id, reviewer_login, state) VALUES (1, 1, 'reviewer1', 'APPROVED')")
    raw_conn.commit()

    contributors = resolve_contributors(raw_conn)

    assert len(contributors) == 1
    assert contributors[0].github_login == "reviewer1"
    assert contributors[0].git_identities == []
