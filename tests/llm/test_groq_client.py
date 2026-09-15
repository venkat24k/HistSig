"""Offline tests using a fake `requests.Session` (same pattern as
tests/collection/test_github_collector.py's FakeSession) — no real
network calls, no real API key needed."""

import pytest
import requests

from src.llm.groq_client import explain_diff


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self._response = response
        self.last_call = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_call = {"url": url, "headers": headers, "json": json, "timeout": timeout}
        return self._response


def test_explain_diff_returns_model_response_text(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    session = FakeSession(FakeResponse({"choices": [{"message": {"content": "  Bumps the version number.  "}}]}))

    result = explain_diff("Release 1.0", "diff --git a/x b/x\n-0.9\n+1.0", session=session)

    assert result == "Bumps the version number."


def test_explain_diff_sends_commit_message_and_diff_in_prompt(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    session = FakeSession(FakeResponse({"choices": [{"message": {"content": "ok"}}]}))

    explain_diff("Fix off-by-one bug", "diff --git a/x b/x\n-i <= n\n+i < n", session=session)

    user_message = session.last_call["json"]["messages"][1]["content"]
    assert "Fix off-by-one bug" in user_message
    assert "i < n" in user_message


def test_explain_diff_truncates_very_large_diffs(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    session = FakeSession(FakeResponse({"choices": [{"message": {"content": "ok"}}]}))
    huge_diff = "x" * 50_000

    explain_diff("msg", huge_diff, session=session)

    user_message = session.last_call["json"]["messages"][1]["content"]
    assert len(user_message) < 20_000  # well under the raw diff size -- truncation actually happened


def test_explain_diff_uses_authorization_header(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "secret-123")
    session = FakeSession(FakeResponse({"choices": [{"message": {"content": "ok"}}]}))

    explain_diff("msg", "diff", session=session)

    assert session.last_call["headers"]["Authorization"] == "Bearer secret-123"


def test_explain_diff_uses_default_model_when_not_overridden(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    session = FakeSession(FakeResponse({"choices": [{"message": {"content": "ok"}}]}))

    explain_diff("msg", "diff", session=session)

    assert session.last_call["json"]["model"] == "openai/gpt-oss-120b"


def test_explain_diff_uses_env_model_override(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "some-other-model")
    session = FakeSession(FakeResponse({"choices": [{"message": {"content": "ok"}}]}))

    explain_diff("msg", "diff", session=session)

    assert session.last_call["json"]["model"] == "some-other-model"


def test_explain_diff_raises_runtime_error_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        explain_diff("msg", "diff")


def test_explain_diff_raises_http_error_on_failed_request(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    session = FakeSession(FakeResponse({"error": "rate limited"}, status_code=429))

    with pytest.raises(requests.HTTPError):
        explain_diff("msg", "diff", session=session)
