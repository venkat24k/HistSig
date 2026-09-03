"""A small in-memory raw-schema database, hand-populated with the specific
edge cases Stage 2 needs to handle correctly (noreply emails, bots,
renames, deletes, reverts) — built directly against src.collection.schema
so it can never silently drift from the real Stage 1 schema."""

import sqlite3

import pytest

from src.collection.schema import create_schema


@pytest.fixture
def raw_conn():
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    conn.execute("INSERT INTO repositories (id, url, name, default_branch, collected_at) VALUES (1, 'https://x/y', 'y', 'main', '2024-01-01')")
    conn.commit()
    return conn
