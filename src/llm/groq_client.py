"""Optional LLM explanation layer (CLAUDE.md Section 9) — diff
explanation only, strictly evidence-grounded, and never used to compute
or validate HistSig's own P/R scores. This module is deliberately
disconnected from every scoring/ranking/divergence path in the codebase:
`src/scoring/`, `src/divergence/`, and everything upstream of them stay
fully testable and runnable with `GROQ_API_KEY` unset (Section 9:
"HistSig must remain independently testable without any LLM in the
loop").

Uses Groq's free tier — an OpenAI-compatible chat completions API — for
the same reason CLAUDE.md's evidence-first flow prefers it: it's free,
fast, and needs only a single API key (see .env.example), chosen
explicitly by the user over the alternatives (Gemini, local Ollama) when
this feature was proposed, not picked unilaterally (Section 25: adding
an LLM dependency needs approval).

The prompt below is the actual enforcement point for CLAUDE.md Section
10's Evidence-First Principle: the model is given nothing but the real
commit message and real diff text already shown elsewhere in the UI, and
is explicitly told not to invent motivation or context beyond that
evidence — this is `Repository evidence -> Explanation`, never
`Repository -> LLM -> Unverified story`.
"""

import os

import requests

_GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
# Groq's available free-tier models change over time (verified live
# against GET /openai/v1/models when this was picked) -- gpt-oss-120b was
# chosen over the smaller gpt-oss-20b and Groq's own "compound" models
# for explanation quality; llama-3.3-70b-versatile, this module's
# original default, had been retired from the free tier by the time this
# was tested. If GROQ_MODEL ever starts 404ing with "model_not_found,"
# that's Groq deprecating a model, not a bug here -- check
# GET https://api.groq.com/openai/v1/models for the current list.
_DEFAULT_MODEL = "openai/gpt-oss-120b"

# A diff can run to hundreds of KB (see src/collection/git_collector.py:
# get_commit_diff's own much larger 200_000-char display truncation) --
# this is a separate, much smaller budget for what actually goes into the
# prompt, chosen for latency/cost on a free tier, not for display.
_MAX_DIFF_CHARS_IN_PROMPT = 8_000

_SYSTEM_PROMPT = (
    "You are helping a software engineer understand one commit's historical "
    "significance in a repository. You will be given the commit's real "
    "message and its real diff. In 2-4 concise sentences, explain what "
    "changed and why it plausibly mattered, using ONLY the evidence given -- "
    "never invent motivation, issue numbers, related context, or events not "
    "present in the message or diff. If the change looks trivial (formatting, "
    "a version bump, a lockfile update), say so plainly instead of overstating "
    "its importance. If the diff doesn't make the reason for the change clear, "
    "say that explicitly rather than guessing."
)


def explain_diff(
    commit_message: str | None,
    diff_text: str,
    session: requests.Session | None = None,
    model: str | None = None,
) -> str:
    """Returns a short natural-language explanation of `diff_text`,
    grounded only in `commit_message` and the diff itself. Raises
    `RuntimeError` if `GROQ_API_KEY` isn't configured, and
    `requests.HTTPError` on a failed request — both left for the caller
    to turn into a clean API response (this module has no opinion on
    HTTP status codes)."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured (see .env.example)")

    session = session or requests.Session()
    model = model or os.environ.get("GROQ_MODEL") or _DEFAULT_MODEL

    truncated_diff = diff_text[:_MAX_DIFF_CHARS_IN_PROMPT]
    user_content = (
        f"Commit message:\n{commit_message or '(no message recorded)'}\n\n"
        f"Diff:\n{truncated_diff}"
    )

    response = session.post(
        _GROQ_CHAT_COMPLETIONS_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            # gpt-oss-120b is a reasoning model: it spends some of this
            # budget on a hidden reasoning trace before the visible
            # answer, unlike a plain chat model where max_tokens is
            # spent entirely on output text. 300 was measured to
            # sometimes truncate before any visible content appeared at
            # all (finish_reason "length" with an empty message.content)
            # -- 600 leaves enough room for both on a real diff.
            "max_tokens": 600,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()
