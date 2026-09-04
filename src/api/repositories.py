"""Read-only data access for the API — lists collected repositories and
their candidate events by scanning data/raw/*.db and data/processed/*.db.
Kept separate from main.py's route wiring so the query logic is testable
without spinning up the FastAPI app.
"""

import sqlite3
from pathlib import Path

DATA_DIR = Path("data")
_RAW_COUNT_TABLES = ("commits", "issues", "pull_requests", "releases")


class RepositoryNotFound(Exception):
    pass


def list_repository_names() -> list[str]:
    raw_dir = DATA_DIR / "raw"
    if not raw_dir.exists():
        return []
    return sorted(p.stem for p in raw_dir.glob("*.db"))


def _open(safe_name: str) -> tuple[sqlite3.Connection, sqlite3.Connection | None]:
    raw_path = DATA_DIR / "raw" / f"{safe_name}.db"
    if not raw_path.exists():
        raise RepositoryNotFound(safe_name)
    raw_conn = sqlite3.connect(raw_path)
    processed_path = DATA_DIR / "processed" / f"{safe_name}.db"
    processed_conn = sqlite3.connect(processed_path) if processed_path.exists() else None
    return raw_conn, processed_conn


def _raw_counts(raw_conn: sqlite3.Connection) -> dict:
    return {table: raw_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in _RAW_COUNT_TABLES}


def _event_counts(processed_conn: sqlite3.Connection | None, repo_id: int) -> dict:
    if processed_conn is None:
        return {}
    try:
        granularities = [row[0] for row in processed_conn.execute(
            "SELECT DISTINCT granularity FROM candidate_events WHERE repo_id = ?", (repo_id,)
        )]
    except sqlite3.OperationalError:
        return {}  # events table doesn't exist yet — Stage 3 hasn't run for this repo
    return {
        g: processed_conn.execute(
            "SELECT COUNT(*) FROM candidate_events WHERE repo_id = ? AND granularity = ?", (repo_id, g)
        ).fetchone()[0]
        for g in granularities
    }


def _contributor_count(processed_conn: sqlite3.Connection | None, repo_id: int) -> int | None:
    if processed_conn is None:
        return None
    try:
        return processed_conn.execute("SELECT COUNT(*) FROM contributors WHERE repo_id = ?", (repo_id,)).fetchone()[0]
    except sqlite3.OperationalError:
        return None  # Stage 2 hasn't run for this repo yet


def list_repositories() -> list[dict]:
    out = []
    for safe_name in list_repository_names():
        raw_conn, processed_conn = _open(safe_name)
        row = raw_conn.execute("SELECT id, url, name, default_branch, collected_at FROM repositories LIMIT 1").fetchone()
        if row is None:
            continue
        repo_id, url, name, default_branch, collected_at = row
        out.append({
            "safe_name": safe_name, "url": url, "name": name, "default_branch": default_branch,
            "collected_at": collected_at, "counts": _raw_counts(raw_conn),
            "contributor_count": _contributor_count(processed_conn, repo_id),
            "event_counts": _event_counts(processed_conn, repo_id),
        })
    return out


def get_repository(safe_name: str) -> dict:
    raw_conn, processed_conn = _open(safe_name)
    row = raw_conn.execute("SELECT id, url, name, default_branch, collected_at FROM repositories LIMIT 1").fetchone()
    if row is None:
        raise RepositoryNotFound(safe_name)
    repo_id, url, name, default_branch, collected_at = row
    return {
        "safe_name": safe_name, "url": url, "name": name, "default_branch": default_branch,
        "collected_at": collected_at, "counts": _raw_counts(raw_conn),
        "contributor_count": _contributor_count(processed_conn, repo_id),
        "event_counts": _event_counts(processed_conn, repo_id),
    }


def _author_dict(processed_conn: sqlite3.Connection, contributor_id: int | None) -> dict | None:
    if contributor_id is None:
        return None
    row = processed_conn.execute(
        "SELECT canonical_name, github_login, is_bot FROM contributors WHERE id = ?", (contributor_id,)
    ).fetchone()
    if row is None:
        return None
    return {"name": row[0], "github_login": row[1], "is_bot": bool(row[2])}


def list_events(safe_name: str, granularity: str, event_type: str | None, limit: int, offset: int) -> dict:
    raw_conn, processed_conn = _open(safe_name)
    if processed_conn is None:
        raise RepositoryNotFound(f"{safe_name} (no processed data yet — run Stage 2/3 first)")
    repo_id = raw_conn.execute("SELECT id FROM repositories LIMIT 1").fetchone()[0]

    where = "WHERE repo_id = ? AND granularity = ?"
    params: list = [repo_id, granularity]
    if event_type:
        where += " AND event_type = ?"
        params.append(event_type)

    total = processed_conn.execute(f"SELECT COUNT(*) FROM candidate_events {where}", params).fetchone()[0]
    rows = processed_conn.execute(
        f"""
        SELECT id, event_type, source_pr_number, primary_commit_hash, title, author_contributor_id, occurred_at
        FROM candidate_events {where}
        ORDER BY occurred_at DESC LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    events = [
        {
            "id": r[0], "event_type": r[1], "source_pr_number": r[2], "primary_commit_hash": r[3],
            "title": r[4], "author": _author_dict(processed_conn, r[5]), "occurred_at": r[6],
        }
        for r in rows
    ]
    return {"total": total, "limit": limit, "offset": offset, "events": events}


def get_event(safe_name: str, event_id: int) -> dict:
    raw_conn, processed_conn = _open(safe_name)
    if processed_conn is None:
        raise RepositoryNotFound(f"{safe_name} (no processed data yet)")

    row = processed_conn.execute(
        """
        SELECT id, granularity, event_type, source_pr_number, primary_commit_hash, title, author_contributor_id, occurred_at
        FROM candidate_events WHERE id = ?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        raise RepositoryNotFound(f"event {event_id} in {safe_name}")

    event_id_, granularity, event_type, pr_number, primary_commit_hash, title, contributor_id, occurred_at = row
    commit_hashes = [r[0] for r in processed_conn.execute("SELECT commit_hash FROM event_commits WHERE event_id = ?", (event_id,))]

    pr_detail = None
    if event_type == "pull_request" and pr_number is not None:
        pr_row = raw_conn.execute(
            "SELECT body, state, base_branch, head_branch, merge_commit_sha FROM pull_requests WHERE number = ?",
            (pr_number,),
        ).fetchone()
        if pr_row:
            pr_detail = {"body": pr_row[0], "state": pr_row[1], "base_branch": pr_row[2], "head_branch": pr_row[3], "merge_commit_sha": pr_row[4]}

    commits = []
    for h in commit_hashes:
        c = raw_conn.execute(
            "SELECT hash, author_name, message, author_date_utc, insertions, deletions FROM commits WHERE hash = ?", (h,)
        ).fetchone()
        commits.append(
            {"hash": h, "author_name": c[1], "message": c[2], "author_date_utc": c[3], "insertions": c[4], "deletions": c[5]}
            if c else {"hash": h, "author_name": None, "message": None, "author_date_utc": None, "insertions": None, "deletions": None}
        )

    return {
        "id": event_id_, "granularity": granularity, "event_type": event_type, "source_pr_number": pr_number,
        "primary_commit_hash": primary_commit_hash, "title": title, "occurred_at": occurred_at,
        "author": _author_dict(processed_conn, contributor_id), "pr_detail": pr_detail, "commits": commits,
    }
