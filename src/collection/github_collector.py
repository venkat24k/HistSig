"""GitHub API collection: GraphQL for issues/PRs/releases, REST for repo
metadata.

Requires GITHUB_TOKEN.

Why GraphQL for the bulk data: a REST-only approach needs one call per PR
for reviews, one for review comments, one for commits, plus one per issue
for comments — for a repository with ~3,700 issues+PRs (pallets/click, used
as the pilot repo) that is over 7,000 individual requests, which exceeds
GitHub's 5,000/hour primary quota on its own, regardless of how well those
calls are parallelized. GraphQL fetches an issue with its comments, or a PR
with its reviews/review-comments/commits, as nested connections inside a
single query, cutting total request count by roughly an order of magnitude.
GitHub's GraphQL rate limit is cost-based rather than one-point-per-call, so
the nested connection sizes below (`_ISSUE_COMMENTS_PER_PAGE` etc.) are kept
modest to keep per-query cost predictable; an issue or PR with more items
than that page size is documented, not silently truncated (see
`IssueRecord.comments_truncated` / `PullRequestRecord.reviews_truncated`).

Both the REST call (repo metadata) and GraphQL calls funnel through
`_send_request`, which backs off correctly for *primary* rate-limit
exhaustion (`X-RateLimit-Remaining: 0` + `X-RateLimit-Reset`, no
`Retry-After` header) as well as the secondary-abuse-detection case (403/429
+ `Retry-After`) — an earlier version only handled the latter and crashed
outright the first time a real collection run against a repo this size
exhausted the primary quota.

Extraction functions take a plain `owner/repo` string and a `requests.Session`
(from `get_session`), and are unit-tested against a minimal fake session
returning canned JSON — see tests/collection/test_github_collector.py — so
no live network access or GitHub-specific mocking library is needed.
"""

import re
import time
from dataclasses import dataclass, field

import requests

API_BASE = "https://api.github.com"
GRAPHQL_URL = f"{API_BASE}/graphql"

# Matches the owner/repo segment right after "github.com" for both HTTPS
# (https://github.com/owner/repo[.git][/]) and SSH (git@github.com:owner/repo.git)
# URLs, and ignores anything after it (e.g. a browser-pasted
# .../owner/repo/tree/main URL) rather than silently misparsing it.
_GITHUB_URL_RE = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?(?:/|$)")


def parse_owner_repo(url: str) -> str:
    match = _GITHUB_URL_RE.search(url.strip())
    if not match:
        raise ValueError(f"Could not parse an owner/repo from {url!r} — expected a github.com HTTPS or SSH URL.")
    return f"{match.group(1)}/{match.group(2)}"

_ISSUE_PAGE_SIZE = 50
_ISSUE_COMMENTS_PER_PAGE = 100
_PR_PAGE_SIZE = 15
_PR_REVIEWS_PER_PAGE = 30
_PR_REVIEW_COMMENTS_PER_PAGE = 20
_PR_COMMITS_PER_PAGE = 100
_PR_COMMENTS_PER_PAGE = 50
_PR_CLOSING_ISSUES_PER_PAGE = 20
_PR_CROSS_REFERENCES_PER_PAGE = 20
_LABELS_PER_PAGE = 20
_RELEASE_PAGE_SIZE = 50


def get_session(token: str, pool_size: int = 16) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    adapter = requests.adapters.HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("https://", adapter)
    return session


_RETRYABLE_STATUSES = (403, 429, 500, 502, 503, 504)


def _send_request(session: requests.Session, method: str, url: str, *, params=None, json=None, max_retries: int = 6) -> requests.Response:
    """Shared REST/GraphQL request path with rate-limit-aware backoff:
    - secondary abuse detection: 403/429 with a `Retry-After` header -> sleep that long.
    - primary quota exhausted: `X-RateLimit-Remaining: 0` with `X-RateLimit-Reset` -> sleep until reset.
    - anything else transient (connection errors, other 403/429, 5xx) -> capped exponential backoff.

    Each attempt raises (or returns) from its *own* current result rather than
    remembering state across iterations — an earlier version stashed the first
    exception seen and re-raised that stale error after the retry budget ran
    out, even when a later attempt had gotten a real, more informative
    response back.
    """
    for attempt in range(max_retries):
        is_last_attempt = attempt == max_retries - 1
        try:
            resp = session.request(method, url, params=params, json=json, timeout=30)
        except requests.RequestException:
            if is_last_attempt:
                raise
            time.sleep(min(2**attempt, 15))
            continue

        if resp.status_code in _RETRYABLE_STATUSES:
            if is_last_attempt:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset_at = resp.headers.get("X-RateLimit-Reset")
            if retry_after:
                # Capped the same way as the primary-rate-limit branch below --
                # an earlier version trusted this server-supplied header with no
                # upper bound at all, which silently stalled a real collection
                # run for 30+ minutes with zero visibility (no crash, no log,
                # just a thread asleep) when GitHub's secondary abuse-detection
                # returned an unexpectedly large value during a burst of large
                # queries against pytest-dev/pytest.
                wait = min(int(retry_after) + 1, 3600)
                if wait > 30:
                    print(f"[github_collector] {resp.status_code} on {url}: sleeping {wait}s (Retry-After)")
                time.sleep(wait)
            elif remaining == "0" and reset_at:
                wait = min(max(int(reset_at) - time.time(), 1) + 2, 3600)
                if wait > 30:
                    print(f"[github_collector] primary rate limit exhausted on {url}: sleeping {wait}s")
                time.sleep(wait)
            else:
                time.sleep(min(2**attempt, 30))
            continue

        resp.raise_for_status()
        return resp

    raise AssertionError("unreachable: loop above always returns or raises on its last iteration")


def _request(session: requests.Session, url: str, params: dict | None = None) -> requests.Response:
    return _send_request(session, "GET", url, params=params)


class GraphQLComplexityExceeded(RuntimeError):
    """Raised when GitHub's GraphQL query-complexity budget is exceeded
    (`errors[*].type == "RESOURCE_LIMITS_EXCEEDED"`). Unlike RATE_LIMITED or
    a transient backend fault, this is deterministic given the same query
    and variables -- retrying unchanged would fail identically every time
    (confirmed live: pytest-dev/pytest's PR query overflowed the budget on
    every node in the page, not one pathological PR, meaning the *page* was
    too large, not any single item in it). A distinct exception from the
    generic transient-error RuntimeError so `_graphql_paginate` can catch
    it specifically and shrink the page size instead of looping forever."""


def _graphql(session: requests.Session, query: str, variables: dict, max_retries: int = 6) -> dict:
    """GitHub signals GraphQL rate/complexity-limit exhaustion inside an HTTP
    200 response (`errors: [{"type": "RATE_LIMITED", ...}]`, `data: null`),
    not via a 403/429 status — so that case is handled here, on top of
    `_send_request`'s transport-level retries, rather than being missed
    entirely. GitHub's own transient internal-engine faults ("Something went
    wrong while executing your query ...") are signaled the same way but
    *without* a `type` key at all (confirmed against a live failing query on
    octocat/Spoon-Knife, a repo with an unusually large PR/issue count) —
    every documented application-level GraphQL error (NOT_FOUND, FORBIDDEN,
    etc.) always carries a `type`, so "no type key" is a safe, specific
    signal for "GitHub's backend faulted, retry," not a catch-all.
    RESOURCE_LIMITS_EXCEEDED raises GraphQLComplexityExceeded immediately
    (see its docstring -- retrying here would be pointless). Any other
    GraphQL error (bad owner/repo, revoked access, etc.) still raises a
    plain RuntimeError immediately with the actual error detail, instead of
    returning a partial `data` dict (e.g. `{"repository": None}`) that would
    otherwise fail confusingly deep inside pagination.

    A real live run against pytest-dev/pytest (dense per-PR review/commit
    history) also surfaced a response that was HTTP 200 (so `_send_request`
    treated it as a normal success) but had a completely empty/invalid
    body -- `resp.json()` raising a raw JSONDecodeError with no retry at
    all, crashing the whole collection run on what was almost certainly a
    transient proxy/CDN glitch, not a real application error. That's
    handled here the same way as any other transient condition: retried
    with backoff, not a fatal parse crash.
    """
    for attempt in range(max_retries):
        resp = _send_request(session, "POST", GRAPHQL_URL, json={"query": query, "variables": variables})
        try:
            payload = resp.json()
        except requests.exceptions.JSONDecodeError:
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"GitHub returned a non-JSON response (HTTP {resp.status_code}) after {max_retries} attempts: "
                    f"{resp.text[:200]!r}"
                )
            time.sleep(min(5 * 2**attempt, 60))
            continue
        errors = payload.get("errors")
        if errors:
            if any(e.get("type") == "RESOURCE_LIMITS_EXCEEDED" for e in errors):
                raise GraphQLComplexityExceeded(f"GitHub GraphQL complexity limit exceeded: {errors}")
            is_transient = all(e.get("type") in ("RATE_LIMITED", None) for e in errors)
            if is_transient and attempt < max_retries - 1:
                time.sleep(min(5 * 2**attempt, 60))
                continue
            raise RuntimeError(f"GitHub GraphQL error: {errors}")
        return payload["data"]
    raise AssertionError("unreachable: loop above always returns or raises on its last iteration")


def _graphql_paginate(
    session: requests.Session, query: str, variables: dict, connection_path: tuple[str, ...],
    page_size_key: str = "pageSize", min_page_size: int = 1,
):
    """Paginates a GraphQL connection. On GraphQLComplexityExceeded, halves
    `variables[page_size_key]` and retries the *same* cursor position (no
    items skipped) rather than giving up -- a page that was too complex at
    the original size usually succeeds at half, since the overflow comes
    from the page's total nested node count, not one outlier item (see
    GraphQLComplexityExceeded's docstring). Once a page succeeds, later
    pages keep using the smaller size rather than growing back -- a repo
    dense enough to overflow once is likely dense throughout, and silently
    growing back would just risk re-discovering the same overflow.
    `variables` is copied, not mutated, so shrinking one connection's pages
    doesn't affect the caller's own dict or any other paginate call reusing
    it. All three current callers (`collect_issues`/`collect_pull_requests`/
    `collect_releases`) name their outer page-size variable "pageSize", so
    the default needs no per-caller wiring.
    """
    variables = dict(variables)
    cursor = None
    while True:
        try:
            data = _graphql(session, query, {**variables, "cursor": cursor})
        except GraphQLComplexityExceeded:
            shrunk = max(variables[page_size_key] // 2, min_page_size)
            if shrunk == variables[page_size_key]:
                raise  # already at the floor -- can't shrink further, genuinely stuck
            variables[page_size_key] = shrunk
            continue
        connection = data
        for key in connection_path:
            connection = connection[key]
        yield from connection["nodes"]
        if not connection["pageInfo"]["hasNextPage"]:
            return
        cursor = connection["pageInfo"]["endCursor"]


def _login(user: dict | None) -> str | None:
    return user.get("login") if user else None


@dataclass
class IssueCommentRecord:
    id: int
    author_login: str | None
    created_at: str | None
    body: str | None


@dataclass
class IssueRecord:
    id: int
    number: int
    title: str
    body: str | None
    state: str
    author_login: str | None
    created_at: str | None
    closed_at: str | None
    updated_at: str | None
    labels: list[str]
    comments: list[IssueCommentRecord] = field(default_factory=list)
    comments_truncated: bool = False


@dataclass
class PRReviewCommentRecord:
    id: int
    review_id: int | None
    author_login: str | None
    created_at: str | None
    body: str | None
    path: str | None


@dataclass
class PRReviewRecord:
    id: int
    reviewer_login: str | None
    state: str
    submitted_at: str | None
    body: str | None


@dataclass
class PRCommentRecord:
    """A PR's general conversation comment — distinct from PRReviewCommentRecord
    (inline code-review comments) and IssueCommentRecord (real issues).
    GitHub's GraphQL PullRequest type exposes this as its own top-level
    `comments` connection, separate from `reviews`."""

    id: int
    author_login: str | None
    created_at: str | None
    body: str | None


@dataclass
class PullRequestRecord:
    id: int
    number: int
    title: str
    body: str | None
    state: str
    author_login: str | None
    created_at: str | None
    merged_at: str | None
    closed_at: str | None
    updated_at: str | None
    base_branch: str | None
    head_branch: str | None
    merge_commit_sha: str | None
    labels: list[str]
    commit_shas: list[str]
    reviews: list[PRReviewRecord] = field(default_factory=list)
    review_comments: list[PRReviewCommentRecord] = field(default_factory=list)
    comments: list[PRCommentRecord] = field(default_factory=list)
    closing_issue_numbers: list[int] = field(default_factory=list)
    reaction_count: int = 0
    # (source_number, referenced_at) for every other issue/PR whose
    # timeline shows it referencing this PR (GitHub's crossReferencedEvent).
    cross_references: list[tuple[int, str | None]] = field(default_factory=list)
    reviews_truncated: bool = False
    commits_truncated: bool = False
    review_comments_truncated: bool = False
    comments_truncated: bool = False
    closing_issues_truncated: bool = False
    # Derived from timelineItems.pageInfo.hasNextPage, NOT totalCount>len(nodes)
    # like every other *_truncated field here. Confirmed against the live API:
    # GitHub's `timelineItems.totalCount` ignores the `itemTypes` filter and
    # reports the count of ALL timeline items (comments, commits, labels,
    # ...), not just CROSS_REFERENCED_EVENT ones -- e.g. pallets/click PR #1
    # returned totalCount=7 with zero actual cross-reference nodes, which
    # would make the totalCount-comparison formula flag nearly every PR as
    # truncated regardless of its real cross-reference count. pageInfo's
    # hasNextPage, by contrast, tracks the cursor over the already-filtered
    # connection and matches the actual node list correctly.
    cross_references_truncated: bool = False


@dataclass
class ReleaseRecord:
    id: int
    tag_name: str
    name: str | None
    created_at: str | None
    published_at: str | None
    author_login: str | None
    body: str | None


_ISSUES_QUERY = """
query($owner: String!, $name: String!, $pageSize: Int!, $commentsPageSize: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: $pageSize, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        databaseId
        number
        title
        body
        state
        author { login }
        createdAt
        closedAt
        updatedAt
        labels(first: 20) { nodes { name } }
        comments(first: $commentsPageSize) {
          totalCount
          nodes { databaseId author { login } createdAt body }
        }
      }
    }
  }
}
"""

_PULL_REQUESTS_QUERY = """
query($owner: String!, $name: String!, $pageSize: Int!, $reviewsPageSize: Int!, $reviewCommentsPageSize: Int!, $commitsPageSize: Int!, $prCommentsPageSize: Int!, $closingIssuesPageSize: Int!, $crossReferencesPageSize: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: $pageSize, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        databaseId
        number
        title
        body
        state
        author { login }
        createdAt
        mergedAt
        closedAt
        updatedAt
        baseRefName
        headRefName
        mergeCommit { oid }
        labels(first: 20) { nodes { name } }
        commits(first: $commitsPageSize) {
          totalCount
          nodes { commit { oid } }
        }
        reviews(first: $reviewsPageSize) {
          totalCount
          nodes {
            databaseId
            author { login }
            state
            submittedAt
            body
            comments(first: $reviewCommentsPageSize) {
              totalCount
              nodes { databaseId author { login } createdAt body path }
            }
          }
        }
        comments(first: $prCommentsPageSize) {
          totalCount
          nodes { databaseId author { login } createdAt body }
        }
        closingIssuesReferences(first: $closingIssuesPageSize) {
          totalCount
          nodes { number }
        }
        reactions { totalCount }
        timelineItems(first: $crossReferencesPageSize, itemTypes: [CROSS_REFERENCED_EVENT]) {
          pageInfo { hasNextPage }
          nodes {
            ... on CrossReferencedEvent {
              createdAt
              source {
                ... on Issue { number }
                ... on PullRequest { number }
              }
            }
          }
        }
      }
    }
  }
}
"""

_RELEASES_QUERY = """
query($owner: String!, $name: String!, $pageSize: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    releases(first: $pageSize, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        databaseId
        tagName
        name
        createdAt
        publishedAt
        author { login }
        description
      }
    }
  }
}
"""


def collect_issues(session: requests.Session, owner_repo: str) -> list[IssueRecord]:
    owner, name = owner_repo.split("/")
    variables = {"owner": owner, "name": name, "pageSize": _ISSUE_PAGE_SIZE, "commentsPageSize": _ISSUE_COMMENTS_PER_PAGE}
    records = []
    for raw in _graphql_paginate(session, _ISSUES_QUERY, variables, ("repository", "issues")):
        comments = [
            IssueCommentRecord(
                id=c["databaseId"],
                author_login=_login(c.get("author")),
                created_at=c.get("createdAt"),
                body=c.get("body"),
            )
            for c in raw["comments"]["nodes"]
        ]
        records.append(
            IssueRecord(
                id=raw["databaseId"],
                number=raw["number"],
                title=raw["title"],
                body=raw.get("body"),
                state=raw["state"].lower(),
                author_login=_login(raw.get("author")),
                created_at=raw.get("createdAt"),
                closed_at=raw.get("closedAt"),
                updated_at=raw.get("updatedAt"),
                labels=[label["name"] for label in raw["labels"]["nodes"]],
                comments=comments,
                comments_truncated=raw["comments"]["totalCount"] > len(comments),
            )
        )
    return records


def collect_pull_requests(session: requests.Session, owner_repo: str) -> list[PullRequestRecord]:
    owner, name = owner_repo.split("/")
    variables = {
        "owner": owner, "name": name, "pageSize": _PR_PAGE_SIZE,
        "reviewsPageSize": _PR_REVIEWS_PER_PAGE, "reviewCommentsPageSize": _PR_REVIEW_COMMENTS_PER_PAGE,
        "commitsPageSize": _PR_COMMITS_PER_PAGE, "prCommentsPageSize": _PR_COMMENTS_PER_PAGE,
        "closingIssuesPageSize": _PR_CLOSING_ISSUES_PER_PAGE,
        "crossReferencesPageSize": _PR_CROSS_REFERENCES_PER_PAGE,
    }
    records = []
    for raw in _graphql_paginate(session, _PULL_REQUESTS_QUERY, variables, ("repository", "pullRequests")):
        reviews: list[PRReviewRecord] = []
        review_comments: list[PRReviewCommentRecord] = []
        review_comments_truncated = False
        for r in raw["reviews"]["nodes"]:
            reviews.append(
                PRReviewRecord(
                    id=r["databaseId"],
                    reviewer_login=_login(r.get("author")),
                    state=r["state"],
                    submitted_at=r.get("submittedAt"),
                    body=r.get("body"),
                )
            )
            review_comments.extend(
                PRReviewCommentRecord(
                    id=c["databaseId"],
                    review_id=r["databaseId"],
                    author_login=_login(c.get("author")),
                    created_at=c.get("createdAt"),
                    body=c.get("body"),
                    path=c.get("path"),
                )
                for c in r["comments"]["nodes"]
            )
            if r["comments"]["totalCount"] > len(r["comments"]["nodes"]):
                review_comments_truncated = True
        pr_comments = [
            PRCommentRecord(
                id=c["databaseId"],
                author_login=_login(c.get("author")),
                created_at=c.get("createdAt"),
                body=c.get("body"),
            )
            for c in raw["comments"]["nodes"]
        ]
        closing_issue_numbers = [n["number"] for n in raw["closingIssuesReferences"]["nodes"]]
        cross_references = [(n["source"]["number"], n.get("createdAt")) for n in raw["timelineItems"]["nodes"]]
        records.append(
            PullRequestRecord(
                id=raw["databaseId"],
                number=raw["number"],
                title=raw["title"],
                body=raw.get("body"),
                state=raw["state"].lower(),
                author_login=_login(raw.get("author")),
                created_at=raw.get("createdAt"),
                merged_at=raw.get("mergedAt"),
                closed_at=raw.get("closedAt"),
                updated_at=raw.get("updatedAt"),
                base_branch=raw.get("baseRefName"),
                head_branch=raw.get("headRefName"),
                merge_commit_sha=(raw.get("mergeCommit") or {}).get("oid"),
                labels=[label["name"] for label in raw["labels"]["nodes"]],
                commit_shas=[n["commit"]["oid"] for n in raw["commits"]["nodes"]],
                reviews=reviews,
                review_comments=review_comments,
                comments=pr_comments,
                closing_issue_numbers=closing_issue_numbers,
                reaction_count=raw["reactions"]["totalCount"],
                cross_references=cross_references,
                reviews_truncated=raw["reviews"]["totalCount"] > len(reviews),
                commits_truncated=raw["commits"]["totalCount"] > len(raw["commits"]["nodes"]),
                review_comments_truncated=review_comments_truncated,
                comments_truncated=raw["comments"]["totalCount"] > len(pr_comments),
                closing_issues_truncated=raw["closingIssuesReferences"]["totalCount"] > len(closing_issue_numbers),
                cross_references_truncated=raw["timelineItems"]["pageInfo"]["hasNextPage"],
            )
        )
    return records


def collect_releases(session: requests.Session, owner_repo: str) -> list[ReleaseRecord]:
    owner, name = owner_repo.split("/")
    variables = {"owner": owner, "name": name, "pageSize": _RELEASE_PAGE_SIZE}
    records = []
    for raw in _graphql_paginate(session, _RELEASES_QUERY, variables, ("repository", "releases")):
        records.append(
            ReleaseRecord(
                id=raw["databaseId"],
                tag_name=raw["tagName"],
                name=raw.get("name"),
                created_at=raw.get("createdAt"),
                published_at=raw.get("publishedAt"),
                author_login=_login(raw.get("author")),
                body=raw.get("description"),
            )
        )
    return records


def get_repo_metadata(session: requests.Session, owner_repo: str) -> dict:
    return _request(session, f"{API_BASE}/repos/{owner_repo}").json()
