"""Neo4j knowledge graph schema (Stage 8) -- iteration 1.

Deliberately minimal per CLAUDE.md Section 7 ("start minimal and extend
only when a concrete query need arises"): three node labels
(Repository, Developer, HistoricalEvent, File) and two relationship types
(AUTHORED, MODIFIES). Issues/PullRequests/Reviews/Releases as their own
nodes are not here yet -- add them when a real query needs them, not
before.

The graph is a single shared database scoped by `Repository` nodes rather
than one database per repo, so cross-repo queries are possible later
without any schema change.
"""

from neo4j import Driver

CONSTRAINTS = [
    "CREATE CONSTRAINT repo_id IF NOT EXISTS FOR (r:Repository) REQUIRE r.safe_name IS UNIQUE",
    "CREATE CONSTRAINT developer_id IF NOT EXISTS FOR (d:Developer) REQUIRE (d.repo, d.contributor_id) IS UNIQUE",
    "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:HistoricalEvent) REQUIRE (e.repo, e.event_id) IS UNIQUE",
    "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE (f.repo, f.path) IS UNIQUE",
]


def create_schema(driver: Driver) -> None:
    with driver.session() as session:
        for stmt in CONSTRAINTS:
            session.run(stmt)


def clear_repo(driver: Driver, safe_name: str) -> None:
    """Deletes every node (and its relationships) scoped to one repo, so a
    repo's slice of the graph can be safely rebuilt from scratch without
    touching any other repo already loaded into the same shared database."""
    with driver.session() as session:
        session.run(
            "MATCH (n) WHERE n.repo = $repo DETACH DELETE n",
            repo=safe_name,
        )
        session.run(
            "MATCH (r:Repository {safe_name: $repo}) DETACH DELETE r",
            repo=safe_name,
        )
