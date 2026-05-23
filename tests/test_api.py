"""Smoke tests for the FastAPI surface.

We mount the real app against the real seeded MAMS database — the
goal is to catch contract drift (e.g. a route referencing a DAL
method that doesn't exist), not unit-test individual routes.
"""

from __future__ import annotations

import pytest

# fastapi is an optional extra (`pip install -e ".[api]"`).
# Skip these tests cleanly if it isn't installed.
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_reports_db_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"


class TestWorldRoutes:
    def test_list_worlds(self, client):
        r = client.get("/api/world/worlds")
        assert r.status_code == 200
        worlds = r.json()
        assert any(w["name"] == "Greywatch" for w in worlds)

    def test_get_world(self, client):
        r = client.get("/api/world/worlds/1")
        assert r.status_code == 200
        assert r.json()["name"] == "Greywatch"

    def test_get_world_404(self, client):
        r = client.get("/api/world/worlds/99999")
        assert r.status_code == 404

    def test_list_characters(self, client):
        r = client.get("/api/world/worlds/1/characters")
        assert r.status_code == 200
        chars = r.json()
        names = {c["name"] for c in chars}
        assert "Varen Indoril" in names
        assert "Ondolemar" in names

    def test_list_locations(self, client):
        r = client.get("/api/world/worlds/1/locations")
        assert r.status_code == 200
        locs = r.json()
        assert all("location_type" in loc for loc in locs)
        # No "description" key — the dataclass doesn't have one
        assert all("description" not in loc for loc in locs)

    def test_list_agents(self, client):
        r = client.get("/api/world/worlds/1/agents")
        assert r.status_code == 200
        assert len(r.json()) == 5


class TestAgentStateRoutes:
    def test_beliefs(self, client):
        # Varen NPC Agent has at least one belief in the seed
        # (the map-split belief)
        r = client.get("/api/world/agents/3/beliefs")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_memories(self, client):
        r = client.get("/api/world/agents/3/memories")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_conflicts(self, client):
        r = client.get("/api/world/conflicts")
        assert r.status_code == 200
        # Seed has one unresolved conflict on a fresh DB
        body = r.json()
        assert isinstance(body, list)


class TestSessionsStart:
    def test_start_returns_real_mams_session_id(self, client):
        r = client.post("/api/sessions/start", json={
            "world_id": 1,
            "director_agent_id": 1,
            "narrative_context": "API smoke test",
            "max_turns": 2,
        })
        assert r.status_code == 200
        body = r.json()
        sid = body["session_id"]
        # The DAL should know about this session
        from story_engine.dal import MamsDAL
        dal: MamsDAL = app.state.dal
        sess = dal.get_session(sid)
        assert sess is not None
        assert sess.status == "active"
        assert sess.narrative_context == "API smoke test"
        # Should NOT collide with id(graph) memory addresses
        assert sid < 1_000_000
