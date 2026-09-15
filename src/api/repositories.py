"""Read-only data access for the API — lists collected repositories and
their candidate events by scanning data/raw/*.db and data/processed/*.db.
Kept separate from main.py's route wiring so the query logic is testable
without spinning up the FastAPI app.
"""

import sqlite3
from pathlib import Path

DATA_DIR = Path("data")
_RAW_COUNT_TABLES = ("commits", "issues", "pull_requests", "releases")

# Matches src/features/storage.py's _FEATURE_COLUMNS — kept as a separate
# list here (rather than importing it) since the API only ever reads this
# table, never writes it, and shouldn't depend on the feature-extraction
# package to stay decoupled per CLAUDE.md Section 17 ("keep research logic
# separate from UI logic").
_P_FEATURE_NAMES = (
    "comment_count", "distinct_commenters", "reviewer_count", "review_rounds",
    "files_changed", "churn", "issue_link_present", "issue_has_label",
    "release_proximity", "reaction_count",
)
_BOOLEAN_P_FEATURES = {"issue_link_present", "issue_has_label"}

# Matches src/features/storage.py's _R_FEATURE_COLUMNS, same
# decoupling reason as _P_FEATURE_NAMES above. "maturity" is kept
# separate from the other three below (see _r_features_dict) since it's
# context every R feature needs, not a weighted feature of its own —
# CLAUDE.md Section 34.
_R_FEATURE_NAMES = ("files_survived", "subsequent_modification_count", "releases_since_count", "later_references_count")


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


def _p_score_dict(processed_conn: sqlite3.Connection, event_id: int) -> dict | None:
    """Returns {"p_score", "features_used", "is_high_p"} or None if Phase 3
    P-scoring (scripts/compute_p_scores.py) hasn't run for this repo yet."""
    try:
        row = processed_conn.execute(
            "SELECT p_score, features_used, is_high_p FROM event_p_scores WHERE event_id = ?", (event_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return {"p_score": row[0], "features_used": row[1], "is_high_p": None if row[2] is None else bool(row[2])}


def _r_score_dict(processed_conn: sqlite3.Connection, event_id: int) -> dict | None:
    """Same shape as _p_score_dict, for event_r_scores (Phase 3, R half —
    scripts/compute_r_scores.py)."""
    try:
        row = processed_conn.execute(
            "SELECT r_score, features_used, is_high_r FROM event_r_scores WHERE event_id = ?", (event_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return {"r_score": row[0], "features_used": row[1], "is_high_r": None if row[2] is None else bool(row[2])}


def _thresholds_for_granularity(processed_conn: sqlite3.Connection, repo_id: int, granularity: str, table: str) -> dict:
    """{event_type: {"threshold_score", "group_size", "top_percentile"}} for
    every scored group in this granularity — lets the UI show *why* a given
    score is or isn't flagged high (the threshold differs per event_type;
    see CLAUDE.md Section 34). {} if that axis's Phase 3 scoring hasn't run
    yet. `table` is always one of this codebase's own two threshold tables
    (p_score_thresholds/r_score_thresholds) — never caller-supplied."""
    try:
        rows = processed_conn.execute(
            f"SELECT event_type, threshold_score, group_size, top_percentile FROM {table} WHERE repo_id = ? AND granularity = ?",
            (repo_id, granularity),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {
        event_type: {"threshold_score": thr, "group_size": size, "top_percentile": pct}
        for event_type, thr, size, pct in rows
    }


def list_events(
    safe_name: str,
    granularity: str,
    event_type: str | None,
    limit: int,
    offset: int,
    high_p: bool | None = None,
    high_r: bool | None = None,
) -> dict:
    raw_conn, processed_conn = _open(safe_name)
    if processed_conn is None:
        raise RepositoryNotFound(f"{safe_name} (no processed data yet — run Stage 2/3 first)")
    repo_id = raw_conn.execute("SELECT id FROM repositories LIMIT 1").fetchone()[0]

    joins: list[str] = []
    where = "WHERE e.repo_id = ? AND e.granularity = ?"
    params: list = [repo_id, granularity]
    if event_type:
        where += " AND e.event_type = ?"
        params.append(event_type)
    # Inner joins deliberately exclude events with no score row at all
    # (that axis's Phase 3 hasn't run) *and* events scored but left NULL
    # (zero applicable features) from both "high" and "rest" — neither is
    # the same as "classified as not high," so neither belongs in a
    # high=False result either (same missing-data principle as the
    # features themselves: never conflate "unknown" with a real 0).
    # high_p and high_r are independent filters and can both be set.
    if high_p is not None:
        joins.append("JOIN event_p_scores ps ON ps.event_id = e.id")
        where += " AND ps.is_high_p = ?"
        params.append(1 if high_p else 0)
    if high_r is not None:
        joins.append("JOIN event_r_scores rs ON rs.event_id = e.id")
        where += " AND rs.is_high_r = ?"
        params.append(1 if high_r else 0)
    join = " ".join(joins)

    # A requested axis's score table may not exist yet for this repo
    # (Phase 3 scoring hasn't run for it) — same "not computed yet" case
    # _thresholds_for_granularity/_p_score_dict/_r_score_dict already
    # handle below, but here it's inside a JOIN, not a plain SELECT, so it
    # surfaces as a query-time OperationalError instead of an empty
    # result. Filtering by an axis that doesn't exist yet can only ever
    # match zero events, never an error.
    try:
        total = processed_conn.execute(f"SELECT COUNT(*) FROM candidate_events e {join} {where}", params).fetchone()[0]
        rows = processed_conn.execute(
            f"""
            SELECT e.id, e.event_type, e.source_pr_number, e.primary_commit_hash, e.title, e.author_contributor_id, e.occurred_at
            FROM candidate_events e {join} {where}
            ORDER BY e.occurred_at DESC LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    except sqlite3.OperationalError:
        total = 0
        rows = []

    events = [
        {
            "id": r[0], "event_type": r[1], "source_pr_number": r[2], "primary_commit_hash": r[3],
            "title": r[4], "author": _author_dict(processed_conn, r[5]), "occurred_at": r[6],
            "p_score": _p_score_dict(processed_conn, r[0]),
            "r_score": _r_score_dict(processed_conn, r[0]),
        }
        for r in rows
    ]
    return {
        "total": total, "limit": limit, "offset": offset, "events": events,
        "p_thresholds": _thresholds_for_granularity(processed_conn, repo_id, granularity, "p_score_thresholds"),
        "r_thresholds": _thresholds_for_granularity(processed_conn, repo_id, granularity, "r_score_thresholds"),
    }


def _p_features_dict(processed_conn: sqlite3.Connection, event_id: int) -> dict | None:
    """Returns {feature_name: {"value": ..., "status": ...}} or None if
    Stage 2's feature extraction hasn't run for this repo yet — distinct
    from an empty dict, which would wrongly imply "ran but found nothing"."""
    try:
        columns = ", ".join(f"{name}, {name}_status" for name in _P_FEATURE_NAMES)
        row = processed_conn.execute(f"SELECT {columns} FROM event_p_features WHERE event_id = ?", (event_id,)).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    result = {}
    for i, name in enumerate(_P_FEATURE_NAMES):
        value, status = row[2 * i], row[2 * i + 1]
        if name in _BOOLEAN_P_FEATURES and value is not None:
            value = bool(value)
        result[name] = {"value": value, "status": status}
    return result


def _r_features_dict(processed_conn: sqlite3.Connection, event_id: int) -> dict | None:
    """Returns {"maturity": {"value","status"}, "features": {name:
    {"value","status"}, ...}} or None if Stage 2/3's R extraction hasn't
    run for this repo yet.

    `maturity` is kept separate from `features` in the response shape
    because it isn't a weighted R feature itself — it's context every
    other R feature needs when its value gets read (CLAUDE.md Section
    34): a low `files_survived` count for an event with `maturity` near 0
    means "too early to judge," not "this didn't matter.\""""
    try:
        columns = ", ".join(f"{name}, {name}_status" for name in _R_FEATURE_NAMES)
        row = processed_conn.execute(
            f"SELECT maturity, maturity_status, {columns} FROM event_r_features WHERE event_id = ?", (event_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    features = {}
    for i, name in enumerate(_R_FEATURE_NAMES):
        value, status = row[2 + 2 * i], row[2 + 2 * i + 1]
        features[name] = {"value": value, "status": status}
    return {"maturity": {"value": row[0], "status": row[1]}, "features": features}


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
        "p_features": _p_features_dict(processed_conn, event_id_),
        "p_score": _p_score_dict(processed_conn, event_id_),
        "r_features": _r_features_dict(processed_conn, event_id_),
        "r_score": _r_score_dict(processed_conn, event_id_),
    }
