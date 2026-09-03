"""Contributor identity resolution (Stage 2).

Raw evidence carries two disjoint identity namespaces that never get
resolved to each other automatically: Git-level identity (commit
author_name/author_email, from `git log`) and GitHub-level identity
(author_login, from the API — issues, PRs, comments, reviews, releases).
The same human is frequently both, under different-looking raw values.

Resolution strategy (deliberately conservative — documented, not fuzzy):
1. Every distinct GitHub login seen anywhere in raw evidence seeds one
   contributor (`identity_confidence="github_login"`).
2. A commit's (name, email) is linked to that same contributor if its email
   is a GitHub "noreply" address (`{id}+{login}@users.noreply.github.com`
   or `{login}@users.noreply.github.com`), since that email format directly
   encodes the login GitHub itself assigned it — high confidence, not a
   guess (`identity_confidence="noreply_email"`).
3. Everything else is clustered by exact raw signal only: by email when
   present, else by name — never by fuzzy name similarity, which risks
   silently merging two different people (`identity_confidence="name_email_pair"`).

This means two accounts belonging to the same real person will NOT be
merged unless linked by (2) — a known, documented limitation, not a
silent gap: CLAUDE.md Section 20 requires missing/uncertain information to
be distinguished, not smoothed over by guessing.
"""

import re
from dataclasses import dataclass, field
from sqlite3 import Connection

_NOREPLY_RE = re.compile(r"^(?:\d+\+)?([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)@users\.noreply\.github\.com$", re.IGNORECASE)


def parse_noreply_login(email: str | None) -> str | None:
    if not email:
        return None
    match = _NOREPLY_RE.match(email.strip())
    return match.group(1) if match else None


def is_bot_login(login: str | None) -> bool:
    """Only GitHub's own bot-account naming convention (`name[bot]`) is
    recognized — a bot account that doesn't follow it (e.g. a legacy
    unsuffixed CI account) will not be flagged. Documented limitation, not
    a silent gap."""
    return bool(login) and login.endswith("[bot]")


@dataclass
class ContributorRecord:
    canonical_name: str | None
    canonical_email: str | None
    github_login: str | None
    is_bot: bool
    identity_confidence: str
    git_identities: list[tuple[str, str]] = field(default_factory=list)
    github_logins: list[str] = field(default_factory=list)

    @property
    def merged_identity_count(self) -> int:
        return len(self.git_identities) + len(self.github_logins)


_GITHUB_LOGIN_SOURCES = (
    ("issues", "author_login"),
    ("issue_comments", "author_login"),
    ("pull_requests", "author_login"),
    ("pr_reviews", "reviewer_login"),
    ("pr_review_comments", "author_login"),
    ("releases", "author_login"),
)


def resolve_contributors(raw_conn: Connection) -> list[ContributorRecord]:
    all_logins: set[str] = set()
    for table, column in _GITHUB_LOGIN_SOURCES:
        for (login,) in raw_conn.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"):
            all_logins.add(login)

    contributors: list[ContributorRecord] = []
    login_to_contributor: dict[str, int] = {}

    for login in sorted(all_logins):
        contributors.append(
            ContributorRecord(
                canonical_name=None, canonical_email=None, github_login=login,
                is_bot=is_bot_login(login), identity_confidence="github_login",
                github_logins=[login],
            )
        )
        login_to_contributor[login] = len(contributors) - 1

    email_to_contributor: dict[str, int] = {}
    name_to_contributor: dict[str, int] = {}

    git_pairs = raw_conn.execute("SELECT DISTINCT author_name, author_email FROM commits").fetchall()
    for name, email in git_pairs:
        email = email or None  # normalize empty-string emails to None, same "no email" case
        login = parse_noreply_login(email)
        if login:
            if login not in login_to_contributor:
                contributors.append(
                    ContributorRecord(
                        canonical_name=name, canonical_email=email, github_login=login,
                        is_bot=is_bot_login(login), identity_confidence="noreply_email",
                        github_logins=[login],
                    )
                )
                login_to_contributor[login] = len(contributors) - 1
            idx = login_to_contributor[login]
            contributors[idx].git_identities.append((name, email))
            if contributors[idx].canonical_name is None:
                contributors[idx].canonical_name = name
            continue

        cluster_map = email_to_contributor if email else name_to_contributor
        key = email if email else f"name-only:{name}"
        if key not in cluster_map:
            contributors.append(
                ContributorRecord(
                    canonical_name=name, canonical_email=email, github_login=None,
                    is_bot=False, identity_confidence="name_email_pair",
                )
            )
            cluster_map[key] = len(contributors) - 1
        contributors[cluster_map[key]].git_identities.append((name, email))

    return contributors
