"""Shared fixtures for MAMS DAL tests.

All tests run against the Greywatch seed data.  The database must already
exist and be seeded (run 00_run_all.sql first).
"""

from __future__ import annotations

import pytest
from psycopg_pool import ConnectionPool

from story_engine.dal.connection import _build_conninfo
from story_engine.dal.mams_dal import MamsDAL


@pytest.fixture(scope="session")
def pool() -> ConnectionPool:
    """A single connection pool shared across the entire test session."""
    p = ConnectionPool(conninfo=_build_conninfo(), min_size=1, max_size=3, open=True)
    yield p
    p.close()


@pytest.fixture(scope="session")
def dal(pool: ConnectionPool) -> MamsDAL:
    """A MamsDAL instance backed by the session-scoped pool."""
    return MamsDAL(pool)


# ── Known IDs from the Greywatch seed data ──────────────────────────
# The seed script uses GENERATED ALWAYS AS IDENTITY and a single DO block,
# so IDs are sequential starting at 1 on a freshly built database.
# These fixtures make tests readable without hard-coding numbers everywhere.

@pytest.fixture(scope="session")
def greywatch_world(dal: MamsDAL):
    w = dal.get_world_by_name("Greywatch")
    assert w is not None, "Greywatch world not found — is the DB seeded?"
    return w


@pytest.fixture(scope="session")
def director_agent(dal: MamsDAL):
    a = dal.get_agent_by_name("Director Agent")
    assert a is not None
    return a


@pytest.fixture(scope="session")
def varen_agent(dal: MamsDAL):
    a = dal.get_agent_by_name("Varen NPC Agent")
    assert a is not None
    return a


@pytest.fixture(scope="session")
def lydia_agent(dal: MamsDAL):
    a = dal.get_agent_by_name("Lydia NPC Agent")
    assert a is not None
    return a


@pytest.fixture(scope="session")
def ondolemar_agent(dal: MamsDAL):
    a = dal.get_agent_by_name("Ondolemar NPC Agent")
    assert a is not None
    return a
