import pytest

from src.events.schema import create_schema as create_events_schema
from src.processing.schema import connect as connect_processed


@pytest.fixture
def processed_conn(tmp_path):
    """A processed-schema database (Stage 2 tables) with the Stage 3
    event tables added on top, matching how form_events.py opens it."""
    conn = connect_processed(str(tmp_path / "processed.db"))
    create_events_schema(conn)
    return conn
