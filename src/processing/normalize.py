"""Stage 2 orchestration: run every normalization step for one repository
and persist the results. See identity.py, commits.py, files.py for the
individual steps and the reasoning behind each.
"""

import sqlite3

from src.processing.commits import RevertInfo, detect_revert
from src.processing.files import build_file_identities
from src.processing.identity import parse_noreply_login, resolve_contributors
from src.processing.storage import (
    insert_commit_annotations,
    insert_contributors,
    insert_data_availability,
    insert_file_identities,
)


def normalize_repository(raw_conn: sqlite3.Connection, processed_conn: sqlite3.Connection, repo_id: int) -> dict:
    contributors = resolve_contributors(raw_conn)
    index_to_db_id = insert_contributors(processed_conn, repo_id, contributors)

    identity_to_contributor_id: dict[tuple[str, str | None], int] = {}
    for index, c in enumerate(contributors):
        db_id = index_to_db_id[index]
        for name, email in c.git_identities:
            identity_to_contributor_id[(name, email)] = db_id

    annotations: list[tuple[str, int | None, RevertInfo]] = []
    for commit_hash, name, email, message in raw_conn.execute("SELECT hash, author_name, author_email, message FROM commits"):
        contributor_id = identity_to_contributor_id.get((name, email or None))
        annotations.append((commit_hash, contributor_id, detect_revert(message)))
    insert_commit_annotations(processed_conn, repo_id, annotations)

    files = build_file_identities(raw_conn)
    insert_file_identities(processed_conn, repo_id, files)

    has_releases = raw_conn.execute("SELECT COUNT(*) FROM releases").fetchone()[0] > 0
    has_pr_reviews = raw_conn.execute("SELECT COUNT(*) FROM pr_reviews").fetchone()[0] > 0
    has_issues = raw_conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] > 0
    earliest_date, latest_date = raw_conn.execute("SELECT MIN(author_date_utc), MAX(author_date_utc) FROM commits").fetchone()
    insert_data_availability(
        processed_conn, repo_id,
        has_releases=has_releases, has_pr_reviews=has_pr_reviews, has_issues=has_issues,
        earliest_commit_date=earliest_date, latest_commit_date=latest_date,
    )

    unresolved_commits = sum(1 for _, contributor_id, _ in annotations if contributor_id is None)
    noreply_links_total = sum(
        1 for c in contributors for _, email in c.git_identities if parse_noreply_login(email)
    )

    return {
        "contributors": len(contributors),
        "contributors_by_confidence": {
            # "confidence" reflects how each contributor record was first
            # established, not how every one of its merged identities was
            # linked — a noreply-email commit by someone already known from
            # GitHub-side evidence (an issue/PR/review) correctly merges
            # into that existing "github_login" contributor rather than
            # creating a separate "noreply_email" one. See
            # git_identities_linked_via_noreply_email for the total count
            # of noreply-email links regardless of which bucket they landed in.
            level: sum(1 for c in contributors if c.identity_confidence == level)
            for level in ("github_login", "noreply_email", "name_email_pair")
        },
        "git_identities_linked_via_noreply_email": noreply_links_total,
        "bots_flagged": sum(1 for c in contributors if c.is_bot),
        "commits_annotated": len(annotations),
        "commits_unresolved_identity": unresolved_commits,
        "reverts_detected": sum(1 for _, _, r in annotations if r.is_revert),
        "reverts_with_resolved_target": sum(1 for _, _, r in annotations if r.is_revert and r.reverts_commit_hash),
        "file_identities": len(files),
        "renamed_files": sum(1 for f in files if f.first_path != f.last_path),
        "deleted_files": sum(1 for f in files if f.is_deleted),
        "has_releases": has_releases,
        "has_pr_reviews": has_pr_reviews,
        "has_issues": has_issues,
    }
