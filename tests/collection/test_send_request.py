"""Tests for the shared request/retry machinery (`_send_request`, `_graphql`)
— this is where the real bugs hit during a live collection run against
pallets/click actually lived (a stale exception masking the real final
error, and GitHub's GraphQL-rate-limit-via-HTTP-200 shape not being
handled at all), so it's tested directly rather than only indirectly
through the higher-level collect_* functions.
"""

import pytest

from src.collection.github_collector import GraphQLComplexityExceeded, _graphql, _graphql_paginate, _send_request


class ScriptedResponse:
    def __init__(self, status_code=200, headers=None, json_data=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self._json}")


class ScriptedSession:
    """Returns each entry from `script` in order; an Exception instance in
    the script is raised instead of returned, simulating a connection error."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def request(self, method, url, params=None, json=None, timeout=None):
        item = self.script[self.calls]
        self.calls += 1
        self.requests_received = getattr(self, "requests_received", [])
        self.requests_received.append(json)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import src.collection.github_collector as mod
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: None)


def test_send_request_raises_the_real_final_error_not_a_stale_earlier_one():
    """Regression test: an earlier version tracked only the first exception
    seen (`last_exc`) and re-raised that stale error once retries ran out,
    even when the actual last attempt returned a real (still-bad) HTTP
    response. It should surface the current 403, not the connection error
    from several attempts ago."""
    import requests
    session = ScriptedSession([
        requests.ConnectionError("boom"),
        ScriptedResponse(403, headers={}, json_data={"message": "secondary rate limit"}),
        ScriptedResponse(403, headers={}, json_data={"message": "secondary rate limit"}),
    ])

    with pytest.raises(RuntimeError, match="HTTP 403"):
        _send_request(session, "GET", "https://api.github.com/x", max_retries=3)


def test_send_request_retries_server_errors():
    session = ScriptedSession([
        ScriptedResponse(502),
        ScriptedResponse(200, json_data={"ok": True}),
    ])

    resp = _send_request(session, "GET", "https://api.github.com/x", max_retries=3)

    assert resp.json() == {"ok": True}


def test_send_request_caps_retry_after_header_instead_of_trusting_it_unbounded(monkeypatch):
    """Regression test: a real collection run against pytest-dev/pytest
    stalled silently for 30+ minutes with zero progress and no error --
    traced to `time.sleep(int(retry_after) + 1)` trusting GitHub's
    Retry-After header with no upper bound at all, unlike the primary-rate-
    limit branch right below it which already caps its wait at 3600s. A
    large (or malformed) Retry-After value must not be able to stall a
    thread for an unbounded amount of time."""
    import src.collection.github_collector as mod
    sleep_calls = []
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    session = ScriptedSession([
        ScriptedResponse(403, headers={"Retry-After": "999999"}, json_data={"message": "secondary rate limit"}),
        ScriptedResponse(200, json_data={"ok": True}),
    ])

    resp = _send_request(session, "GET", "https://api.github.com/x", max_retries=3)

    assert resp.json() == {"ok": True}
    assert sleep_calls == [3600]  # capped, not the raw 1,000,000-second value


def test_send_request_does_not_retry_non_retryable_client_errors():
    session = ScriptedSession([ScriptedResponse(404, json_data={"message": "Not Found"})])

    with pytest.raises(RuntimeError, match="HTTP 404"):
        _send_request(session, "GET", "https://api.github.com/x", max_retries=5)

    assert session.calls == 1  # no retry wasted on a non-retryable error


def test_graphql_backs_off_and_retries_on_rate_limited_error_in_200_response():
    """GitHub signals GraphQL rate/complexity-limit exhaustion via HTTP 200
    with a populated `errors` array, not a 403/429 — `_send_request` alone
    can't see this; `_graphql` has to handle it."""
    session = ScriptedSession([
        ScriptedResponse(200, json_data={"errors": [{"type": "RATE_LIMITED", "message": "..."}], "data": None}),
        ScriptedResponse(200, json_data={"data": {"repository": {"issues": {"nodes": []}}}}),
    ])

    data = _graphql(session, "query { x }", {}, max_retries=3)

    assert data == {"repository": {"issues": {"nodes": []}}}


def test_graphql_retries_transient_internal_error_with_no_type_field():
    """Regression test: a live collection run against octocat/Spoon-Knife
    (a repo with an unusually large PR/issue count) hit GitHub's own
    transient internal-engine fault ("Something went wrong while executing
    your query ..."), which comes back as an `errors` entry with no `type`
    key at all — this was previously treated like any other application
    error and raised immediately after one attempt, with no retry."""
    session = ScriptedSession([
        ScriptedResponse(200, json_data={
            "errors": [{"message": "Something went wrong while executing your query on ... Please include `X` when reporting this issue."}],
            "data": None,
        }),
        ScriptedResponse(200, json_data={"data": {"repository": {"pullRequests": {"nodes": []}}}}),
    ])

    data = _graphql(session, "query { x }", {}, max_retries=3)

    assert data == {"repository": {"pullRequests": {"nodes": []}}}


def test_graphql_raises_immediately_with_detail_on_non_rate_limit_error():
    """A `data.repository: null` response (bad owner/repo, revoked access)
    must not be silently swallowed just because `data` is a truthy dict —
    it should raise with the actual error detail, not surface as an opaque
    TypeError somewhere deep in pagination."""
    session = ScriptedSession([
        ScriptedResponse(200, json_data={
            "data": {"repository": None},
            "errors": [{"type": "NOT_FOUND", "message": "Could not resolve to a Repository"}],
        }),
    ])

    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        _graphql(session, "query { x }", {}, max_retries=3)

    assert session.calls == 1


def test_graphql_retries_on_empty_non_json_200_response():
    """Regression test: a real live run against pytest-dev/pytest hit an
    HTTP 200 response with a completely empty body -- _send_request treats
    any 2xx as success (it only inspects status codes), so this reached
    resp.json() and crashed with a raw JSONDecodeError and no retry at all,
    killing the whole collection run on what was almost certainly a
    transient proxy/CDN glitch."""
    class EmptyBodyResponse(ScriptedResponse):
        def json(self):
            import requests as _requests
            raise _requests.exceptions.JSONDecodeError("Expecting value", "", 0)

    session = ScriptedSession([
        EmptyBodyResponse(200),
        ScriptedResponse(200, json_data={"data": {"repository": {"pullRequests": {"nodes": []}}}}),
    ])

    data = _graphql(session, "query { x }", {}, max_retries=3)

    assert data == {"repository": {"pullRequests": {"nodes": []}}}


def test_graphql_raises_complexity_exceeded_as_its_own_type_without_retrying():
    """RESOURCE_LIMITS_EXCEEDED is deterministic given the same query/variables
    (confirmed live on pytest-dev/pytest) -- _graphql must not burn retries
    on it the way it does for RATE_LIMITED, and must raise the dedicated
    GraphQLComplexityExceeded type so a caller (_graphql_paginate) can catch
    it specifically rather than treating it like any other fatal error."""
    session = ScriptedSession([
        ScriptedResponse(200, json_data={
            "data": None,
            "errors": [{"type": "RESOURCE_LIMITS_EXCEEDED", "message": "Resource limits for this query exceeded."}],
        }),
    ])

    with pytest.raises(GraphQLComplexityExceeded):
        _graphql(session, "query { x }", {}, max_retries=6)

    assert session.calls == 1  # no retry wasted -- retrying unchanged would fail identically


def _page_response(nodes, has_next=False, cursor=None):
    return ScriptedResponse(200, json_data={
        "data": {"repository": {"pullRequests": {
            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
            "nodes": nodes,
        }}}
    })


def _complexity_error_response():
    return ScriptedResponse(200, json_data={
        "data": None,
        "errors": [{"type": "RESOURCE_LIMITS_EXCEEDED", "message": "Resource limits for this query exceeded."}],
    })


def test_graphql_paginate_halves_page_size_and_retries_same_cursor_on_complexity_exceeded():
    """Regression test for the real pytest-dev/pytest collection failure:
    a page of 15 PRs overflowed GitHub's complexity budget on every node in
    the page, not one pathological PR -- meaning the page itself was too
    large. _graphql_paginate should halve pageSize and retry the same page
    (same cursor, no items skipped) rather than giving up or skipping data."""
    session = ScriptedSession([
        _complexity_error_response(),  # pageSize=16 -> too big
        _page_response([{"id": 1}, {"id": 2}]),  # pageSize=8 -> succeeds, last page
    ])

    results = list(_graphql_paginate(
        session, "query { x }", {"pageSize": 16}, ("repository", "pullRequests"),
    ))

    assert results == [{"id": 1}, {"id": 2}]
    assert session.calls == 2
    sent_page_sizes = [r["variables"]["pageSize"] for r in session.requests_received]
    assert sent_page_sizes == [16, 8]  # second attempt used the halved size
    assert session.requests_received[1]["variables"]["cursor"] is None  # retried the SAME page, didn't advance


def test_graphql_paginate_keeps_shrunk_page_size_for_later_pages():
    """Once a page is shrunk, later pages should keep using the smaller
    size rather than growing back -- a repo dense enough to overflow once
    is likely dense throughout (see _graphql_paginate's docstring)."""
    session = ScriptedSession([
        _complexity_error_response(),  # pageSize=16 -> too big
        _page_response([{"id": 1}], has_next=True, cursor="c1"),  # pageSize=8 -> succeeds, more pages
        _page_response([{"id": 2}]),  # should still be called with pageSize=8, not 16
    ])

    results = list(_graphql_paginate(
        session, "query { x }", {"pageSize": 16}, ("repository", "pullRequests"),
    ))

    assert results == [{"id": 1}, {"id": 2}]
    sent_page_sizes = [r["variables"]["pageSize"] for r in session.requests_received]
    assert sent_page_sizes == [16, 8, 8]


def test_graphql_paginate_raises_once_page_size_floor_is_reached():
    """If even the minimum page size overflows, this is a genuinely stuck
    state (not transient) -- must raise rather than loop forever re-trying
    size 1 against size 1."""
    session = ScriptedSession([_complexity_error_response()] * 3)

    with pytest.raises(GraphQLComplexityExceeded):
        list(_graphql_paginate(
            session, "query { x }", {"pageSize": 1}, ("repository", "pullRequests"),
            min_page_size=1,
        ))

    assert session.calls == 1  # pageSize already at the floor -- no point retrying at all
