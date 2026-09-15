import pytest

from src.events.schema import create_schema as create_events_schema
from src.features.schema import create_r_schema, create_schema as create_features_schema
from src.processing.schema import connect as connect_processed


@pytest.fixture
def processed_conn(tmp_path):
    conn = connect_processed(str(tmp_path / "processed.db"))
    create_events_schema(conn)
    create_features_schema(conn)
    create_r_schema(conn)
    return conn
