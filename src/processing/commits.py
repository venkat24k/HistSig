"""Revert-commit detection (Stage 2).

Git's standard `git revert` commit message includes a machine-readable
line ("This reverts commit <hash>."), which is parsed here for a
high-confidence link back to the original commit. A commit whose message
merely starts with "Revert " but lacks that line (e.g. a manual revert,
or GitHub's squash-revert UI, which doesn't always include the full
hash) is still flagged as a revert, just without a resolved target hash —
distinguishing "known revert, unknown target" from "not a revert" rather
than conflating them (CLAUDE.md Section 20).
"""

import re
from dataclasses import dataclass

_REVERTS_HASH_RE = re.compile(r"This reverts commit ([0-9a-f]{7,40})", re.IGNORECASE)


@dataclass
class RevertInfo:
    is_revert: bool
    reverts_commit_hash: str | None


def detect_revert(message: str) -> RevertInfo:
    message = message or ""
    match = _REVERTS_HASH_RE.search(message)
    reverts_hash = match.group(1) if match else None
    is_revert = bool(reverts_hash) or message.strip().startswith("Revert ")
    return RevertInfo(is_revert=is_revert, reverts_commit_hash=reverts_hash)
