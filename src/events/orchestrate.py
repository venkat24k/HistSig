"""Stage 3 orchestration: form candidate events under one or more
granularities and persist them, for one repository."""

import sqlite3

from src.events.formation import form_events
from src.events.storage import insert_events

DEFAULT_GRANULARITIES = ("pr_bundle", "commit_level")


def form_and_store_events(
    raw_conn: sqlite3.Connection, processed_conn: sqlite3.Connection, repo_id: int,
    granularities: tuple[str, ...] = DEFAULT_GRANULARITIES,
) -> dict:
    results = {}
    for granularity in granularities:
        events = form_events(raw_conn, granularity)
        results[granularity] = insert_events(processed_conn, repo_id, granularity, events)
    return results
