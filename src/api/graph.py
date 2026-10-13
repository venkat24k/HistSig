"""Read-only Neo4j query access for the API -- returns a repo's knowledge
graph slice as plain nodes/edges, shaped for Cytoscape.js on the frontend.
Kept separate from repositories.py (which reads SQLite) the same way that
module is kept separate from main.py's route wiring: different data store,
different concerns, same "keep stages separate" principle (CLAUDE.md
Section 17).

The driver is created lazily and cached at module scope -- a single
long-lived driver (it manages its own connection pool internally) is the
documented neo4j-python-driver pattern, not a new connection per request.
"""

import os

from neo4j import Driver, GraphDatabase

_driver: Driver | None = None


class GraphNotConfigured(Exception):
    pass


def _get_driver() -> Driver:
    global _driver
    if _driver is None:
        uri = os.environ.get("NEO4J_URI")
        username = os.environ.get("NEO4J_USERNAME")
        password = os.environ.get("NEO4J_PASSWORD")
        if not (uri and username and password):
            raise GraphNotConfigured("NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD not set")
        _driver = GraphDatabase.driver(uri, auth=(username, password))
    return _driver


def get_repo_graph(safe_name: str, only_scored: bool = True, limit: int = 1500) -> dict:
    """Returns {nodes: [...], edges: [...]} for one repo's graph slice.

    `only_scored` (default) restricts HistoricalEvent nodes to those with a
    quadrant classification, which keeps the first render legible instead
    of dumping every routine_noise event onto the canvas at once -- this is
    a display default the frontend can turn off, not a change to what's
    stored in the graph itself.
    """
    driver = _get_driver()
    event_filter = "WHERE e.quadrant IS NOT NULL" if only_scored else ""
    with driver.session() as session:
        rows = session.run(
            f"""
            MATCH (r:Repository {{safe_name: $repo}})-[:HAS_EVENT]->(e:HistoricalEvent)
            {event_filter}
            WITH e LIMIT $limit
            OPTIONAL MATCH (d:Developer)-[:AUTHORED]->(e)
            OPTIONAL MATCH (e)-[:MODIFIES]->(f:File)
            RETURN e, d, collect(DISTINCT f) AS files
            """,
            repo=safe_name, limit=limit,
        )
        nodes = {}
        edges = []
        for row in rows:
            e = row["e"]
            event_node_id = f"event:{e['event_id']}"
            if event_node_id not in nodes:
                nodes[event_node_id] = {
                    "id": event_node_id, "type": "HistoricalEvent",
                    "label": e.get("title") or f"event #{e['event_id']}",
                    "event_type": e.get("event_type"), "quadrant": e.get("quadrant"),
                    "p_score": e.get("p_score"), "r_score": e.get("r_score"),
                    "is_high_p": e.get("is_high_p"), "is_high_r": e.get("is_high_r"),
                    "occurred_at": e.get("occurred_at"),
                }

            d = row["d"]
            if d is not None:
                dev_node_id = f"dev:{d['contributor_id']}"
                if dev_node_id not in nodes:
                    nodes[dev_node_id] = {
                        "id": dev_node_id, "type": "Developer",
                        "label": d.get("github_login") or d.get("name") or f"contributor #{d['contributor_id']}",
                        "is_bot": d.get("is_bot"),
                    }
                edges.append({"id": f"{dev_node_id}->{event_node_id}", "source": dev_node_id, "target": event_node_id, "type": "AUTHORED"})

            for f in row["files"]:
                file_node_id = f"file:{f['path']}"
                if file_node_id not in nodes:
                    nodes[file_node_id] = {"id": file_node_id, "type": "File", "label": f["path"]}
                edges.append({"id": f"{event_node_id}->{file_node_id}", "source": event_node_id, "target": file_node_id, "type": "MODIFIES"})

    return {"nodes": list(nodes.values()), "edges": edges}
