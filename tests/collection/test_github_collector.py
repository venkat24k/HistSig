"""Tests use a minimal fake `requests.Session` that returns canned GraphQL
response bodies keyed by (query, cursor), instead of live network calls or
a mocking library — the collector only needs `.request(method, url,
params=..., json=..., timeout=...) -> response-like`.
"""

import pytest

from src.collection.github_collector import collect_issues, collect_pull_requests, collect_releases, parse_owner_repo


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/pallets/click", "pallets/click"),
    ("https://github.com/pallets/click.git", "pallets/click"),
    ("https://github.com/pallets/click/", "pallets/click"),
    ("git@github.com:pallets/click.git", "pallets/click"),
    ("https://github.com/pallets/click/tree/main", "pallets/click"),
    ("https://github.com/pallets/click/pull/123", "pallets/click"),
])
def test_parse_owner_repo_handles_common_url_shapes(url, expected):
    assert parse_owner_repo(url) == expected


def test_parse_owner_repo_rejects_non_github_url():
    with pytest.raises(ValueError):
        parse_owner_repo("https://gitlab.com/pallets/click")


class FakeResponse:
    def __init__(self, data, status_code=200, headers=None):
        self._data = data
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """`pages` is a list of GraphQL `data` payloads returned in order, one
    per request — enough for these tests since each test issues requests
    against a single query type in sequence."""

    def __init__(self, pages: list[dict]):
        self.pages = list(pages)
        self.calls = 0

    def request(self, method, url, params=None, json=None, timeout=None):
        page = self.pages[self.calls]
        self.calls += 1
        return FakeResponse({"data": page})


def _user(login):
    return {"login": login}


def _page_info(has_next=False, cursor=None):
    return {"hasNextPage": has_next, "endCursor": cursor}


def test_collect_issues_basic():
    issue_node = {
        "databaseId": 1, "number": 10, "title": "Bug report", "body": "it broke", "state": "CLOSED",
        "author": _user("alice"), "createdAt": "2024-01-01T00:00:00Z", "closedAt": "2024-01-02T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z", "labels": {"nodes": [{"name": "bug"}]},
        "comments": {"totalCount": 1, "nodes": [
            {"databaseId": 100, "author": _user("bob"), "createdAt": "2024-01-01T12:00:00Z", "body": "same here"}
        ]},
    }
    session = FakeSession([
        {"repository": {"issues": {"pageInfo": _page_info(), "nodes": [issue_node]}}}
    ])

    result = collect_issues(session, "o/r")

    assert len(result) == 1
    record = result[0]
    assert record.number == 10
    assert record.state == "closed"
    assert record.labels == ["bug"]
    assert len(record.comments) == 1
    assert record.comments[0].author_login == "bob"
    assert record.comments_truncated is False


def test_collect_issues_flags_truncated_comments():
    issue_node = {
        "databaseId": 1, "number": 10, "title": "Popular issue", "body": "", "state": "OPEN",
        "author": _user("alice"), "createdAt": "2024-01-01T00:00:00Z", "closedAt": None,
        "updatedAt": "2024-01-01T00:00:00Z", "labels": {"nodes": []},
        "comments": {"totalCount": 500, "nodes": [
            {"databaseId": 100, "author": _user("bob"), "createdAt": "2024-01-01T12:00:00Z", "body": "1"}
        ]},
    }
    session = FakeSession([
        {"repository": {"issues": {"pageInfo": _page_info(), "nodes": [issue_node]}}}
    ])

    result = collect_issues(session, "o/r")

    assert result[0].comments_truncated is True


def test_collect_issues_paginates_across_multiple_requests():
    def make_issue(n):
        return {
            "databaseId": n, "number": n, "title": "t", "body": "", "state": "OPEN",
            "author": _user("a"), "createdAt": "2024-01-01T00:00:00Z", "closedAt": None,
            "updatedAt": "2024-01-01T00:00:00Z", "labels": {"nodes": []},
            "comments": {"totalCount": 0, "nodes": []},
        }
    session = FakeSession([
        {"repository": {"issues": {"pageInfo": _page_info(has_next=True, cursor="abc"), "nodes": [make_issue(1)]}}},
        {"repository": {"issues": {"pageInfo": _page_info(), "nodes": [make_issue(2)]}}},
    ])

    result = collect_issues(session, "o/r")

    assert [r.number for r in result] == [1, 2]
    assert session.calls == 2


def test_collect_pull_requests_includes_reviews_and_review_comments_and_commits():
    pr_node = {
        "databaseId": 1, "number": 5, "title": "Add feature", "body": "desc", "state": "MERGED",
        "author": _user("dave"), "createdAt": "2024-01-01T00:00:00Z", "mergedAt": "2024-01-03T00:00:00Z",
        "closedAt": "2024-01-03T00:00:00Z", "updatedAt": "2024-01-03T00:00:00Z",
        "baseRefName": "main", "headRefName": "feature-branch",
        "mergeCommit": {"oid": "cafebabe"}, "labels": {"nodes": [{"name": "enhancement"}]},
        "commits": {"totalCount": 1, "nodes": [{"commit": {"oid": "deadbeef"}}]},
        "reviews": {"totalCount": 1, "nodes": [
            {
                "databaseId": 1, "author": _user("reviewer1"), "state": "APPROVED",
                "submittedAt": "2024-01-02T00:00:00Z", "body": "lgtm",
                "comments": {"totalCount": 1, "nodes": [
                    {"databaseId": 2, "author": _user("reviewer1"), "createdAt": "2024-01-02T00:00:00Z",
                     "body": "nit: rename this", "path": "src/foo.py"}
                ]},
            }
        ]},
        "comments": {"totalCount": 1, "nodes": [
            {"databaseId": 3, "author": _user("dave"), "createdAt": "2024-01-01T05:00:00Z", "body": "PTAL"}
        ]},
        "closingIssuesReferences": {"totalCount": 2, "nodes": [{"number": 42}, {"number": 43}]},
        "reactions": {"totalCount": 3},
    }
    session = FakeSession([
        {"repository": {"pullRequests": {"pageInfo": _page_info(), "nodes": [pr_node]}}}
    ])

    result = collect_pull_requests(session, "o/r")

    assert len(result) == 1
    record = result[0]
    assert record.number == 5
    assert record.state == "merged"
    assert record.base_branch == "main"
    assert record.head_branch == "feature-branch"
    assert record.commit_shas == ["deadbeef"]
    assert record.commits_truncated is False
    assert len(record.reviews) == 1
    assert record.reviews[0].reviewer_login == "reviewer1"
    assert len(record.review_comments) == 1
    assert record.review_comments[0].path == "src/foo.py"
    assert record.review_comments[0].review_id == 1
    assert len(record.comments) == 1
    assert record.comments[0].author_login == "dave"
    assert record.comments[0].body == "PTAL"
    assert record.comments_truncated is False
    assert record.closing_issue_numbers == [42, 43]
    assert record.closing_issues_truncated is False
    assert record.reaction_count == 3


def test_collect_pull_requests_flags_truncated_closing_issues():
    pr_node = {
        "databaseId": 1, "number": 5, "title": "t", "body": "", "state": "OPEN",
        "author": _user("dave"), "createdAt": "2024-01-01T00:00:00Z", "mergedAt": None,
        "closedAt": None, "updatedAt": "2024-01-01T00:00:00Z",
        "baseRefName": "main", "headRefName": "feature-branch",
        "mergeCommit": None, "labels": {"nodes": []},
        "commits": {"totalCount": 0, "nodes": []},
        "reviews": {"totalCount": 0, "nodes": []},
        "comments": {"totalCount": 0, "nodes": []},
        "closingIssuesReferences": {"totalCount": 5, "nodes": [{"number": 1}]},
        "reactions": {"totalCount": 0},
    }
    session = FakeSession([
        {"repository": {"pullRequests": {"pageInfo": _page_info(), "nodes": [pr_node]}}}
    ])

    result = collect_pull_requests(session, "o/r")

    assert result[0].closing_issue_numbers == [1]
    assert result[0].closing_issues_truncated is True


def test_collect_pull_requests_flags_truncated_general_comments():
    pr_node = {
        "databaseId": 1, "number": 5, "title": "t", "body": "", "state": "OPEN",
        "author": _user("dave"), "createdAt": "2024-01-01T00:00:00Z", "mergedAt": None,
        "closedAt": None, "updatedAt": "2024-01-01T00:00:00Z",
        "baseRefName": "main", "headRefName": "feature-branch",
        "mergeCommit": None, "labels": {"nodes": []},
        "commits": {"totalCount": 0, "nodes": []},
        "reviews": {"totalCount": 0, "nodes": []},
        "comments": {"totalCount": 40, "nodes": [
            {"databaseId": 3, "author": _user("dave"), "createdAt": "2024-01-01T05:00:00Z", "body": "1"}
        ]},
        "closingIssuesReferences": {"totalCount": 0, "nodes": []},
        "reactions": {"totalCount": 0},
    }
    session = FakeSession([
        {"repository": {"pullRequests": {"pageInfo": _page_info(), "nodes": [pr_node]}}}
    ])

    result = collect_pull_requests(session, "o/r")

    assert result[0].comments_truncated is True


def test_collect_releases():
    release_node = {
        "databaseId": 1, "tagName": "v1.0.0", "name": "First release",
        "createdAt": "2024-01-01T00:00:00Z", "publishedAt": "2024-01-01T00:00:00Z",
        "author": _user("maintainer"), "description": "Initial release notes",
    }
    session = FakeSession([
        {"repository": {"releases": {"pageInfo": _page_info(), "nodes": [release_node]}}}
    ])

    result = collect_releases(session, "o/r")

    assert len(result) == 1
    assert result[0].tag_name == "v1.0.0"
    assert result[0].author_login == "maintainer"


def test_collect_releases_handles_missing_author():
    release_node = {
        "databaseId": 1, "tagName": "v1.0.0", "name": None,
        "createdAt": "2024-01-01T00:00:00Z", "publishedAt": None, "author": None, "description": None,
    }
    session = FakeSession([
        {"repository": {"releases": {"pageInfo": _page_info(), "nodes": [release_node]}}}
    ])

    result = collect_releases(session, "o/r")

    assert result[0].author_login is None
    assert result[0].published_at is None
