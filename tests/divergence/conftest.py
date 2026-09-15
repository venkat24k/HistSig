import pytest

from src.divergence.schema import create_schema as create_divergence_schema
from src.events.schema import create_schema as create_events_schema
from src.processing.schema import connect as connect_processed
from src.scoring.schema import create_r_schema as create_r_scoring_schema
from src.scoring.schema import create_schema as create_scoring_schema


@pytest.fixture
def processed_conn(tmp_path):
    conn = connect_processed(str(tmp_path / "processed.db"))
    create_events_schema(conn)
    create_scoring_schema(conn)
    create_r_scoring_schema(conn)
    create_divergence_schema(conn)
    return conn
