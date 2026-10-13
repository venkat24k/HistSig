"""Neo4j ingestion (Stage 8) -- iteration 1.

Reads already-computed data straight from a repo's processed SQLite db
(events, scores, divergence, contributors, file history) and writes it
into Neo4j as Developer/HistoricalEvent/File nodes connected by
AUTHORED/MODIFIES relationships. Pure transform -- no new methodology,
no re-derivation of P/R scores; this stage trusts what Phase 3/4 already
computed and stored, the same way the API backend does.

Batched via UNWIND rather than one Cypher statement per row -- the
difference matters once a repo has hundreds of events (see CLAUDE.md
Section 34's `subsequent_modification_count` lesson about per-row queries
not scaling; same shape of fix applied here before it was ever a problem).
"""

import sqlite3

from neo4j import Driver

_BATCH_SIZE = 500


def _batched(rows, size=_BATCH_SIZE):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def load_repo(driver: Driver, processed_conn: sqlite3.Connection, safe_name: str, granularity: str = "pr_bundle") -> dict:
    """Loads one repo's slice of the graph. Call schema.clear_repo() first
    if re-running against a repo already in the graph -- this does not
    deduplicate or merge, it assumes a clean slate for that repo."""
    processed_conn.row_factory = sqlite3.Row
    summary = {"developers": 0, "events": 0, "files": 0, "authored_rels": 0, "modifies_rels": 0}

    with driver.session() as session:
        session.run("MERGE (r:Repository {safe_name: $repo})", repo=safe_name)

        # Developers
        developers = processed_conn.execute(
            "SELECT id, canonical_name, github_login, is_bot FROM contributors"
        ).fetchall()
        dev_rows = [
            {"repo": safe_name, "contributor_id": d["id"], "name": d["canonical_name"],
             "github_login": d["github_login"], "is_bot": bool(d["is_bot"])}
            for d in developers
        ]
        for batch in _batched(dev_rows):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (d:Developer {repo: row.repo, contributor_id: row.contributor_id})
                SET d.name = row.name, d.github_login = row.github_login, d.is_bot = row.is_bot
                WITH d, row
                MATCH (r:Repository {safe_name: row.repo})
                MERGE (r)-[:HAS_CONTRIBUTOR]->(d)
                """,
                rows=batch,
            )
        summary["developers"] = len(dev_rows)

        # HistoricalEvents (joined with P/R scores and divergence -- all optional,
        # since a repo may not have every stage run yet)
        events = processed_conn.execute(
            """
            SELECT ce.id, ce.event_type, ce.source_pr_number, ce.primary_commit_hash,
                   ce.title, ce.occurred_at, ce.author_contributor_id,
                   ps.p_score, ps.is_high_p,
                   rs.r_score, rs.is_high_r,
                   dv.quadrant
            FROM candidate_events ce
            LEFT JOIN event_p_scores ps ON ps.event_id = ce.id
            LEFT JOIN event_r_scores rs ON rs.event_id = ce.id
            LEFT JOIN event_divergence dv ON dv.event_id = ce.id
            WHERE ce.granularity = ?
            """,
            (granularity,),
        ).fetchall()
        event_rows = [
            {
                "repo": safe_name, "event_id": e["id"], "event_type": e["event_type"],
                "source_pr_number": e["source_pr_number"], "title": e["title"],
                "occurred_at": e["occurred_at"], "author_contributor_id": e["author_contributor_id"],
                "p_score": e["p_score"], "is_high_p": bool(e["is_high_p"]) if e["is_high_p"] is not None else None,
                "r_score": e["r_score"], "is_high_r": bool(e["is_high_r"]) if e["is_high_r"] is not None else None,
                "quadrant": e["quadrant"],
            }
            for e in events
        ]
        for batch in _batched(event_rows):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (e:HistoricalEvent {repo: row.repo, event_id: row.event_id})
                SET e.event_type = row.event_type, e.source_pr_number = row.source_pr_number,
                    e.title = row.title, e.occurred_at = row.occurred_at,
                    e.p_score = row.p_score, e.is_high_p = row.is_high_p,
                    e.r_score = row.r_score, e.is_high_r = row.is_high_r,
                    e.quadrant = row.quadrant
                WITH e, row
                MATCH (r:Repository {safe_name: row.repo})
                MERGE (r)-[:HAS_EVENT]->(e)
                WITH e, row
                MATCH (d:Developer {repo: row.repo, contributor_id: row.author_contributor_id})
                MERGE (d)-[:AUTHORED]->(e)
                """,
                rows=batch,
            )
        summary["events"] = len(event_rows)
        summary["authored_rels"] = sum(1 for e in event_rows if e["author_contributor_id"] is not None)

        # Files touched per event, via event_commits -> file_path_history
        file_touches = processed_conn.execute(
            """
            SELECT DISTINCT ec.event_id, fph.path
            FROM event_commits ec
            JOIN file_path_history fph ON fph.commit_hash = ec.commit_hash
            JOIN candidate_events ce ON ce.id = ec.event_id
            WHERE ce.granularity = ?
            """,
            (granularity,),
        ).fetchall()
        distinct_files = sorted({row["path"] for row in file_touches})
        file_rows = [{"repo": safe_name, "path": p} for p in distinct_files]
        for batch in _batched(file_rows):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (f:File {repo: row.repo, path: row.path})
                WITH f, row
                MATCH (r:Repository {safe_name: row.repo})
                MERGE (r)-[:HAS_FILE]->(f)
                """,
                rows=batch,
            )
        summary["files"] = len(file_rows)

        touch_rows = [{"repo": safe_name, "event_id": t["event_id"], "path": t["path"]} for t in file_touches]
        for batch in _batched(touch_rows):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (e:HistoricalEvent {repo: row.repo, event_id: row.event_id})
                MATCH (f:File {repo: row.repo, path: row.path})
                MERGE (e)-[:MODIFIES]->(f)
                """,
                rows=batch,
            )
        summary["modifies_rels"] = len(touch_rows)

    return summary
