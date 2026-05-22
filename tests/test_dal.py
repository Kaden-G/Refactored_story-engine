"""Tests for the MAMS data-access layer against the Greywatch seed data.

Run with:  pytest tests/ -v

Prerequisites:
  - PostgreSQL 16 running locally
  - MAMS database created and seeded:
      dropdb mams && createdb mams
      psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
  - .env file with correct MAMS_DB_* vars (or defaults match your setup)
"""

from __future__ import annotations

from decimal import Decimal

from story_engine.dal.models import (
    Agent,
    AgentBeliefResult,
    Belief,
    BeliefDivergence,
    Character,
    Conflict,
    DecisionRecord,
    EventKnowledgeStatus,
    Location,
    LocationNode,
    LocationOccupant,
    Memory,
    SessionSummary,
    UnresolvedConflict,
    World,
)


# ── World / entity lookups ──────────────────────────────────────────

class TestWorldLookups:
    def test_greywatch_exists(self, greywatch_world):
        assert isinstance(greywatch_world, World)
        assert greywatch_world.name == "Greywatch"

    def test_get_world_by_id(self, dal, greywatch_world):
        w = dal.get_world(greywatch_world.world_id)
        assert w is not None
        assert w.name == "Greywatch"

    def test_get_world_not_found(self, dal):
        assert dal.get_world(99999) is None


class TestAgentLookups:
    def test_get_agents_returns_five(self, dal, greywatch_world):
        agents = dal.get_agents(greywatch_world.world_id)
        assert len(agents) == 5
        assert all(isinstance(a, Agent) for a in agents)

    def test_director_agent(self, director_agent):
        assert director_agent.name == "Director Agent"
        assert director_agent.is_active is True

    def test_agent_by_name_not_found(self, dal):
        assert dal.get_agent_by_name("Nonexistent Agent") is None


class TestCharacterLookups:
    def test_seven_characters(self, dal, greywatch_world):
        chars = dal.get_characters(greywatch_world.world_id)
        assert len(chars) == 7
        names = {c.name for c in chars}
        assert "Varen Indoril" in names
        assert "Ondolemar" in names

    def test_character_by_name(self, dal, greywatch_world):
        c = dal.get_character_by_name("Lydia", greywatch_world.world_id)
        assert c is not None
        assert isinstance(c, Character)
        assert c.character_type == "person"


class TestLocationLookups:
    def test_five_locations(self, dal, greywatch_world):
        locs = dal.get_locations(greywatch_world.world_id)
        assert len(locs) == 5
        names = {loc.name for loc in locs}
        assert "Greywatch Lodge" in names
        assert "Markarth" in names


# ── SQL functions ───────────────────────────────────────────────────

class TestGetConflictCount:
    def test_varen_has_one_conflict(self, dal, varen_agent):
        count = dal.get_conflict_count(varen_agent.agent_id)
        assert count >= 1

    def test_lydia_has_zero_conflicts(self, dal, lydia_agent):
        count = dal.get_conflict_count(lydia_agent.agent_id)
        assert count == 0

    def test_ondolemar_has_one_conflict(self, dal, ondolemar_agent):
        count = dal.get_conflict_count(ondolemar_agent.agent_id)
        assert count >= 1


class TestGetLocationOccupants:
    def test_greywatch_lodge_has_four(self, dal, greywatch_world):
        lodge = None
        for loc in dal.get_locations(greywatch_world.world_id):
            if loc.name == "Greywatch Lodge":
                lodge = loc
                break
        assert lodge is not None
        occupants = dal.get_location_occupants(lodge.location_id)
        assert len(occupants) == 4
        assert all(isinstance(o, LocationOccupant) for o in occupants)
        names = {o.character_name for o in occupants}
        assert "Varen Indoril" in names
        assert "Lydia" in names

    def test_markarth_has_two(self, dal, greywatch_world):
        markarth = None
        for loc in dal.get_locations(greywatch_world.world_id):
            if loc.name == "Markarth":
                markarth = loc
                break
        assert markarth is not None
        occupants = dal.get_location_occupants(markarth.location_id)
        assert len(occupants) == 2
        names = {o.character_name for o in occupants}
        assert "Sylara" in names
        assert "Ondolemar" in names


class TestGetAgentBelief:
    def test_varen_belief_about_map_split(self, dal, varen_agent):
        # Find the map-split event
        events = dal.get_events_for_session(1)
        map_split = [e for e in events if "map is split" in e.description]
        assert len(map_split) == 1
        beliefs = dal.get_agent_belief(
            varen_agent.agent_id, "event", map_split[0].event_id,
        )
        assert len(beliefs) >= 1
        assert all(isinstance(b, AgentBeliefResult) for b in beliefs)
        assert beliefs[0].confidence >= Decimal("0.90")

    def test_lydia_has_no_map_split_belief(self, dal, lydia_agent):
        events = dal.get_events_for_session(1)
        map_split = [e for e in events if "map is split" in e.description]
        assert len(map_split) == 1
        beliefs = dal.get_agent_belief(
            lydia_agent.agent_id, "event", map_split[0].event_id,
        )
        assert len(beliefs) == 0


# ── Composite queries (the 10 from 08_queries.sql) ──────────────────

class TestQuery1AgentMemories:
    def test_varen_has_two_memories(self, dal, varen_agent):
        mems = dal.get_agent_memories(varen_agent.agent_id)
        assert len(mems) == 2
        assert all(isinstance(m, Memory) for m in mems)
        contents = {m.content for m in mems}
        assert any("Coin" in c for c in contents)

    def test_ondolemar_has_one_memory(self, dal, ondolemar_agent):
        mems = dal.get_agent_memories(ondolemar_agent.agent_id)
        assert len(mems) == 1
        assert "probationary" in mems[0].content


class TestQuery2UnresolvedConflicts:
    def test_at_least_one_unresolved(self, dal):
        conflicts = dal.get_unresolved_conflicts()
        assert len(conflicts) >= 1
        assert all(isinstance(c, UnresolvedConflict) for c in conflicts)
        # The seeded conflict is Varen vs Ondolemar
        agents_involved = set()
        for c in conflicts:
            agents_involved.add(c.agent_1)
            agents_involved.add(c.agent_2)
        assert "Varen NPC Agent" in agents_involved
        assert "Ondolemar NPC Agent" in agents_involved


class TestQuery4BeliefDivergence:
    def test_map_split_divergence(self, dal):
        events = dal.get_events_for_session(1)
        map_split = [e for e in events if "map is split" in e.description]
        assert len(map_split) == 1
        div = dal.get_belief_divergence("event", map_split[0].event_id)
        assert len(div) >= 2
        assert all(isinstance(d, BeliefDivergence) for d in div)
        agents = {d.agent for d in div}
        assert "Varen NPC Agent" in agents
        assert "Ondolemar NPC Agent" in agents


class TestQuery5SessionDecisions:
    def test_session_one_has_decisions(self, dal):
        decisions = dal.get_session_decisions(1)
        assert len(decisions) >= 1
        assert all(isinstance(d, DecisionRecord) for d in decisions)
        assert any("propagat" in d.description.lower() for d in decisions)


class TestQuery6RelationshipHistory:
    def test_varen_ondolemar(self, dal):
        history = dal.get_relationship_history("Varen Indoril", "Ondolemar")
        assert len(history) >= 1
        assert history[0].relationship == "distrusts"
        assert history[0].intensity == Decimal("0.60")


class TestQuery7EventKnowledgeStatus:
    def test_map_split_knowledge(self, dal):
        events = dal.get_events_for_session(1)
        map_split = [e for e in events if "map is split" in e.description]
        assert len(map_split) == 1
        statuses = dal.get_event_knowledge_status(map_split[0].event_id)
        assert len(statuses) >= 2
        assert all(isinstance(s, EventKnowledgeStatus) for s in statuses)
        status_map = {s.agent: s.knowledge_status for s in statuses}
        # Lydia does NOT know about the map split (by design)
        assert status_map.get("Lydia NPC Agent") == "does NOT know"
        # Varen does know
        assert "knows" in status_map.get("Varen NPC Agent", "")


class TestQuery8LocationHierarchy:
    def test_hierarchy_includes_greywatch(self, dal, greywatch_world):
        nodes = dal.get_location_hierarchy(greywatch_world.world_id)
        assert len(nodes) >= 5
        assert all(isinstance(n, LocationNode) for n in nodes)
        paths = [n.path for n in nodes]
        assert any("Greywatch Lodge" in p for p in paths)
        # Greywatch Lodge is a child of Falkreath Hold
        greywatch_node = [n for n in nodes if n.name == "Greywatch Lodge"][0]
        assert greywatch_node.depth == 2
        assert "Falkreath Hold > Greywatch Lodge" in greywatch_node.path


class TestQuery9ConflictCountByAgent:
    def test_returns_npc_agents(self, dal):
        counts = dal.get_conflict_counts_by_agent()
        assert len(counts) >= 3
        names = {c["agent"] for c in counts}
        assert "Varen NPC Agent" in names


class TestQuery10SessionSummary:
    def test_session_one_summary(self, dal):
        summary = dal.get_session_summary(1)
        assert summary is not None
        assert isinstance(summary, SessionSummary)
        assert summary.status == "active"
        assert summary.events >= 3
        assert summary.decisions >= 1

    def test_nonexistent_session(self, dal):
        assert dal.get_session_summary(99999) is None


# ── Write operations ────────────────────────────────────────────────

class TestStartSession:
    def test_start_and_end_session(self, dal, greywatch_world, director_agent):
        sid = dal.start_session(
            greywatch_world.world_id,
            director_agent.agent_id,
            "Test session from pytest",
        )
        assert isinstance(sid, int)
        assert sid > 0

        # verify it exists
        s = dal.get_session(sid)
        assert s is not None
        assert s.status == "active"
        assert s.narrative_context == "Test session from pytest"

        # end it
        dal.end_session(sid, "completed")
        s = dal.get_session(sid)
        assert s.status == "completed"
        assert s.ended_at is not None


class TestCreateEvent:
    def test_create_event(self, dal, greywatch_world):
        # get a location and event type
        locs = dal.get_locations(greywatch_world.world_id)
        etypes = dal.get_event_types()
        dialogue_type = [et for et in etypes if et.label == "dialogue"][0]

        eid = dal.create_event(
            world_id=greywatch_world.world_id,
            location_id=locs[0].location_id,
            event_type_id=dialogue_type.event_type_id,
            description="Test event from pytest",
        )
        assert isinstance(eid, int)
        e = dal.get_event(eid)
        assert e is not None
        assert e.description == "Test event from pytest"


class TestCreateBelief:
    def test_create_belief_returns_id(self, dal, varen_agent, greywatch_world):
        locs = dal.get_locations(greywatch_world.world_id)
        bid = dal.create_belief(
            agent_id=varen_agent.agent_id,
            subject_type="location",
            subject_id=locs[0].location_id,
            belief_content="Test belief from pytest",
            confidence=0.50,
        )
        assert isinstance(bid, int)
        # low confidence (0.50) should NOT trigger conflict detection
        beliefs = dal.get_agent_belief(
            varen_agent.agent_id, "location", locs[0].location_id,
        )
        assert any(b.belief_id == bid for b in beliefs)


class TestCreateMemory:
    def test_create_and_deactivate_memory(self, dal, varen_agent, greywatch_world):
        mid = dal.create_memory(
            agent_id=varen_agent.agent_id,
            world_id=greywatch_world.world_id,
            content="Test memory from pytest",
            confidence=0.75,
        )
        assert isinstance(mid, int)
        mems = dal.get_agent_memories(varen_agent.agent_id)
        assert any(m.memory_id == mid for m in mems)

        # deactivate it
        dal.deactivate_memory(mid)
        mems = dal.get_agent_memories(varen_agent.agent_id, active_only=True)
        assert all(m.memory_id != mid for m in mems)


class TestCharacterLocation:
    def test_get_current_location(self, dal, greywatch_world):
        varen = dal.get_character_by_name("Varen Indoril", greywatch_world.world_id)
        assert varen is not None
        loc = dal.get_character_current_location(varen.character_id)
        assert loc is not None
        location = dal.get_location(loc.location_id)
        assert location is not None
        assert location.name == "Greywatch Lodge"
