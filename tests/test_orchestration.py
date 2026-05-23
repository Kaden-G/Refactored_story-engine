"""Tests for the LangGraph orchestration layer.

These exercise the rule-based fallback path (no LLM) so they run
deterministically. The seed has one unresolved Varen-vs-Ondolemar
conflict that the Lore-keeper should resolve via the rule-based
fallback, leaving the database with that conflict closed and a new
decision logged.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from story_engine.orchestration import build_director_graph
from story_engine.orchestration.nodes import (
    _serialize_conflicts,
    make_close_session_node,
    make_lorekeeper_node,
    make_npc_node,
    make_open_session_node,
    make_process_beliefs_node,
    make_process_events_node,
    make_writer_node,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _new_session_state(dal, greywatch_world, director_agent) -> dict:
    """Open a fresh session and return a merged StoryState dict.

    LangGraph normally merges each node's partial update into the
    running state; tests that call a node directly need the same
    merged shape, so we splice the input keys back in.
    """
    inputs = {
        "world_id": greywatch_world.world_id,
        "director_agent_id": director_agent.agent_id,
        "narrative_context": "test session",
    }
    update = make_open_session_node(dal)(inputs)
    return {**inputs, **update}


# ── _serialize_conflicts ────────────────────────────────────────────


class TestSerializeConflicts:
    def test_includes_belief_and_agent_ids(self, dal):
        conflicts = _serialize_conflicts(dal)
        # Seed has exactly one unresolved conflict (Varen vs Ondolemar)
        assert len(conflicts) >= 1
        first = conflicts[0]
        for key in (
            "conflict_id", "agent_1", "agent_id_1", "belief_id_1",
            "belief_1", "agent_2", "agent_id_2", "belief_id_2", "belief_2",
        ):
            assert key in first, f"missing key: {key}"


# ── open_session ────────────────────────────────────────────────────


class TestOpenSessionNode:
    def test_opens_session_and_hydrates_contexts(
        self, dal, greywatch_world, director_agent,
    ):
        state = _new_session_state(dal, greywatch_world, director_agent)

        assert state["session_id"] > 0
        assert state["turn_number"] == 0
        assert state["should_end"] is False
        assert state["pending_events"] == []
        assert state["pending_beliefs"] == []

        # All 5 seed agents should be hydrated
        assert len(state["agent_contexts"]) == 5

        # The director's context carries the real DB label
        director_ctx = state["agent_contexts"][director_agent.agent_id]
        assert director_ctx.agent_type == "Director"

    def test_agent_types_use_real_labels(
        self, dal, greywatch_world, director_agent, varen_agent,
    ):
        state = _new_session_state(dal, greywatch_world, director_agent)
        types = {ctx.agent_type for ctx in state["agent_contexts"].values()}
        # Seed has Director + Specialist + 3 NPCs
        assert "Director" in types
        assert "Specialist" in types
        assert "NPC" in types
        # NPC agents have character_id set
        varen_ctx = state["agent_contexts"][varen_agent.agent_id]
        assert varen_ctx.agent_type == "NPC"
        assert varen_ctx.character_id is not None

    def test_reuses_caller_supplied_session_id(
        self, dal, greywatch_world, director_agent,
    ):
        # Open a session out-of-band, then have the node reuse it.
        sid = dal.start_session(
            greywatch_world.world_id,
            director_agent.agent_id,
            "pre-opened",
        )
        node = make_open_session_node(dal)
        state = node({
            "session_id": sid,
            "world_id": greywatch_world.world_id,
            "director_agent_id": director_agent.agent_id,
            "narrative_context": "ignored — already opened",
        })
        assert state["session_id"] == sid


# ── lorekeeper_act ──────────────────────────────────────────────────


class TestLorekeeperResolution:
    def test_rule_based_resolves_existing_conflicts(
        self, dal, greywatch_world, director_agent,
    ):
        """Rule-based Lore-keeper picks belief_id_1 and persists via DAL."""
        state = _new_session_state(dal, greywatch_world, director_agent)
        before = state["unresolved_conflicts"]
        assert len(before) >= 1
        target_cid = before[0]["conflict_id"]
        expected_winner = before[0]["belief_id_1"]

        node = make_lorekeeper_node(dal, llm=None)
        result = node(state)

        # The state update should report fewer (or zero) unresolved conflicts.
        after = result["unresolved_conflicts"]
        assert all(c["conflict_id"] != target_cid for c in after)

        # And the DB should reflect that.
        cs = dal.get_all_conflicts(resolved=True)
        assert any(c.conflict_id == target_cid for c in cs)

        # The losing belief is now superseded_by = expected_winner
        from story_engine.dal.models import Belief
        with dal._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT belief_id FROM belief WHERE superseded_by = %s",
                    (expected_winner,),
                )
                superseded = cur.fetchall()
        assert len(superseded) >= 1

    def test_no_op_when_no_conflicts(
        self, dal, greywatch_world, director_agent,
    ):
        # Resolve everything first so the LK has nothing to do.
        state = _new_session_state(dal, greywatch_world, director_agent)
        make_lorekeeper_node(dal, llm=None)(state)

        # Refresh and call again
        state2 = _new_session_state(dal, greywatch_world, director_agent)
        result = make_lorekeeper_node(dal, llm=None)(state2)
        assert "no conflicts" in result["messages"][0].content.lower() \
            or "lore is consistent" in result["messages"][0].content.lower() \
            or result["unresolved_conflicts"] == []


# ── writer_act / npc_act emit pending events ────────────────────────


class TestNodeEmitsPendingEvents:
    def test_writer_emits_environmental_event(
        self, dal, greywatch_world, director_agent,
    ):
        state = _new_session_state(dal, greywatch_world, director_agent)
        state["current_plan"] = "describe the lodge at dawn"
        node = make_writer_node(dal, llm=None)
        result = node(state)
        pending = result.get("pending_events", [])
        assert len(pending) == 1
        env = dal.get_event_type_by_label("environmental")
        assert pending[0]["event_type_id"] == env.event_type_id

    def test_npc_emits_dialogue_at_character_location(
        self, dal, greywatch_world, director_agent, varen_agent,
    ):
        state = _new_session_state(dal, greywatch_world, director_agent)
        state["active_agent_id"] = varen_agent.agent_id
        state["current_plan"] = "say something in character"
        node = make_npc_node(dal, llm=None)
        result = node(state)
        pending = result.get("pending_events", [])
        assert len(pending) == 1
        dialogue = dal.get_event_type_by_label("dialogue")
        assert pending[0]["event_type_id"] == dialogue.event_type_id
        # Varen is at Greywatch Lodge per the seed
        assert pending[0]["location_id"] is not None


# ── process_events flushes pending events to MAMS ───────────────────


class TestProcessEvents:
    def test_pending_events_are_persisted(
        self, dal, greywatch_world, director_agent,
    ):
        state = _new_session_state(dal, greywatch_world, director_agent)
        sid = state["session_id"]
        env = dal.get_event_type_by_label("environmental")

        state["pending_events"] = [{
            "event_type_id": env.event_type_id,
            "location_id": None,
            "description": "test environmental event from orchestration test",
        }]

        node = make_process_events_node(dal)
        result = node(state)

        # pending_events should be cleared after flush
        assert result["pending_events"] == []

        # The event should now live in MAMS, attached to the session
        events = dal.get_events_for_session(sid)
        assert any(
            "test environmental event from orchestration test" in e.description
            for e in events
        )


# ── End-to-end graph run ────────────────────────────────────────────


class TestFullGraphRun:
    def test_rule_based_session_resolves_conflict_and_persists_events(
        self, dal, greywatch_world, director_agent,
    ):
        """One full Director loop should:

        1. Open a session
        2. Resolve the seed conflict (rule-based Lore-keeper)
        3. Persist at least one event from NPC/Writer turns
        4. Close the session with status='completed'
        """
        graph = build_director_graph(dal, llm=None, max_turns=4)
        result = graph.invoke({
            "world_id": greywatch_world.world_id,
            "director_agent_id": director_agent.agent_id,
            "narrative_context": "end-to-end test",
        })

        sid = result["session_id"]

        # Session is closed
        sess = dal.get_session(sid)
        assert sess is not None
        assert sess.status == "completed"
        assert sess.ended_at is not None

        # At least one event persisted from a Writer or NPC turn
        events = dal.get_events_for_session(sid)
        assert len(events) >= 1

        # The Varen-vs-Ondolemar conflict (or any pre-existing) is resolved
        # by the rule-based Lore-keeper.
        unresolved_after = dal.get_unresolved_conflicts()
        # Any conflict that existed at session open is now resolved.
        assert len(result["unresolved_conflicts"]) == 0 or all(
            c["conflict_id"] not in {u.conflict_id for u in unresolved_after}
            for c in result.get("unresolved_conflicts", [])
        )
