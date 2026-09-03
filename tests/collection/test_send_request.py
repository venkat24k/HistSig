"""Tests for the shared request/retry machinery (`_send_request`, `_graphql`)
— this is where the real bugs hit during a live collection run against
pallets/click actually lived (a stale exception masking the real final
error, and GitHub's GraphQL-rate-limit-via-HTTP-200 shape not being
handled at all), so it's tested directly rather than only indirectly
through the higher-level collect_* functions.
"""

import pytest

from src.collection.github_collector import _graphql, _send_request


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
