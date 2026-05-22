"""Node functions for the Director StateGraph.

Each function is a LangGraph node: it receives StoryState, does work
(calling the DAL for durable reads/writes, calling an LLM for generation),
and returns a partial state update.

No node should import psycopg or touch the database directly — all DB
access goes through the MamsDAL instance injected at graph-build time.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from story_engine.dal.mams_dal import MamsDAL
from story_engine.orchestration.state import AgentContext, StoryState


# ── Node factories ──────────────────────────────────────────────────
# Each factory takes a MamsDAL (and optionally an LLM) and returns a
# node function with the signature (state: StoryState) -> dict.
# This keeps the DAL out of global scope and makes testing easy.


def make_open_session_node(dal: MamsDAL):
    """Create a node that opens a MAMS session and hydrates agent contexts."""

    def open_session(state: StoryState) -> dict:
        world_id = state["world_id"]
        director_agent_id = state["director_agent_id"]
        narrative_context = state.get("narrative_context", "")

        # 1. Open session in MAMS
        session_id = dal.start_session(
            world_id, director_agent_id, narrative_context,
        )

        # 2. Hydrate agent contexts from MAMS
        agents = dal.get_agents(world_id)
        agent_contexts: dict[int, AgentContext] = {}

        for agent in agents:
            # find the character this agent portrays (if any)
            char_id = None
            char_name = None
            # check agent_character mapping
            beliefs_raw = dal.get_beliefs_for_agent(agent.agent_id)
            memories_raw = dal.get_agent_memories(agent.agent_id)
            known_raw = dal.get_knowledge_events_for_agent(agent.agent_id)

            agent_contexts[agent.agent_id] = AgentContext(
                agent_id=agent.agent_id,
                agent_name=agent.name,
                agent_type="director" if agent.agent_id == director_agent_id else "participant",
                character_id=char_id,
                character_name=char_name,
                memories=[m.content for m in memories_raw],
                beliefs=[
                    {
                        "belief_id": b.belief_id,
                        "subject_type": b.subject_type,
                        "subject_id": b.subject_id,
                        "content": b.belief_content,
                        "confidence": float(b.confidence),
                    }
                    for b in beliefs_raw
                ],
                known_events=[
                    f"event_{ke.event_id} (via {ke.learned_via})"
                    for ke in known_raw
                ],
            )

        # 3. Load any unresolved conflicts
        conflicts = dal.get_unresolved_conflicts()
        unresolved = [
            {
                "conflict_id": c.conflict_id,
                "agent_1": c.agent_1,
                "belief_1": c.belief_1,
                "agent_2": c.agent_2,
                "belief_2": c.belief_2,
            }
            for c in conflicts
        ]

        return {
            "session_id": session_id,
            "agent_contexts": agent_contexts,
            "unresolved_conflicts": unresolved,
            "turn_number": 0,
            "pending_events": [],
            "pending_beliefs": [],
            "should_end": False,
            "error": None,
            "messages": [
                SystemMessage(
                    content=(
                        f"Session {session_id} opened for world {world_id}. "
                        f"{len(agents)} agents enrolled. "
                        f"{len(unresolved)} unresolved conflict(s) carried forward."
                    )
                )
            ],
        }

    return open_session


def make_director_plan_node(dal: MamsDAL, llm=None):
    """Create a node where the Director decides what to do next.

    If no LLM is provided, uses a simple rule-based fallback
    (useful for testing the round-trip without an API key).
    """

    def director_plan(state: StoryState) -> dict:
        turn = state.get("turn_number", 0)
        conflicts = state.get("unresolved_conflicts", [])
        contexts = state.get("agent_contexts", {})

        if llm is not None:
            # Build a prompt for the Director LLM
            system_prompt = (
                "You are the Director agent of a multi-agent narrative system. "
                "You decide which agent acts next and what narrative beat to pursue. "
                "You have access to the following agent contexts and any unresolved conflicts.\n\n"
                f"Turn: {turn}\n"
                f"Unresolved conflicts: {len(conflicts)}\n"
                f"Agents: {[c.agent_name for c in contexts.values()]}\n"
            )
            if conflicts:
                system_prompt += "\nConflicts:\n"
                for c in conflicts:
                    system_prompt += (
                        f"  - {c['agent_1']}: \"{c['belief_1']}\"\n"
                        f"    vs {c['agent_2']}: \"{c['belief_2']}\"\n"
                    )

            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content="What should happen next in this session?"),
            ])
            plan = response.content
        else:
            # Rule-based fallback (no LLM)
            if conflicts:
                plan = (
                    f"Turn {turn}: {len(conflicts)} unresolved conflict(s) detected. "
                    "Priority: review and resolve conflicts before advancing narrative."
                )
            elif turn == 0:
                plan = (
                    f"Turn {turn}: Session opened. "
                    "Assess current world state and advance the narrative."
                )
            else:
                plan = f"Turn {turn}: Continue narrative progression."

        # Decide whether to end (simple: cap at a max turn count for now)
        max_turns = 3
        should_end = turn >= max_turns

        return {
            "current_plan": plan,
            "turn_number": turn + 1,
            "should_end": should_end,
            "messages": [
                AIMessage(content=f"[Director] {plan}")
            ],
        }

    return director_plan


def make_process_events_node(dal: MamsDAL):
    """Create a node that flushes pending events to MAMS."""

    def process_events(state: StoryState) -> dict:
        pending = state.get("pending_events", [])
        session_id = state["session_id"]
        messages = []

        for evt in pending:
            event_id = dal.create_event(
                world_id=state["world_id"],
                location_id=evt.get("location_id"),
                event_type_id=evt["event_type_id"],
                description=evt["description"],
                session_id=session_id,
            )
            # Propagate knowledge to agents present at the location
            if evt.get("location_id") is not None:
                dal.propagate_event(event_id)

            messages.append(
                AIMessage(
                    content=f"[System] Event {event_id} created and propagated: {evt['description']}"
                )
            )

        # Refresh conflicts after new events/beliefs may have been created
        conflicts = dal.get_unresolved_conflicts()
        unresolved = [
            {
                "conflict_id": c.conflict_id,
                "agent_1": c.agent_1,
                "belief_1": c.belief_1,
                "agent_2": c.agent_2,
                "belief_2": c.belief_2,
            }
            for c in conflicts
        ]

        return {
            "pending_events": [],
            "unresolved_conflicts": unresolved,
            "messages": messages,
        }

    return process_events


def make_process_beliefs_node(dal: MamsDAL):
    """Create a node that flushes pending beliefs to MAMS."""

    def process_beliefs(state: StoryState) -> dict:
        pending = state.get("pending_beliefs", [])
        messages = []

        for b in pending:
            belief_id = dal.create_belief(
                agent_id=b["agent_id"],
                subject_type=b["subject_type"],
                subject_id=b["subject_id"],
                belief_content=b["belief_content"],
                confidence=b.get("confidence", 1.0),
            )
            messages.append(
                AIMessage(
                    content=(
                        f"[System] Belief {belief_id} recorded for agent {b['agent_id']}: "
                        f"{b['belief_content'][:80]}..."
                    )
                )
            )

        # Refresh conflicts (trigger may have created new ones)
        conflicts = dal.get_unresolved_conflicts()
        unresolved = [
            {
                "conflict_id": c.conflict_id,
                "agent_1": c.agent_1,
                "belief_1": c.belief_1,
                "agent_2": c.agent_2,
                "belief_2": c.belief_2,
            }
            for c in conflicts
        ]

        return {
            "pending_beliefs": [],
            "unresolved_conflicts": unresolved,
            "messages": messages,
        }

    return process_beliefs


def make_close_session_node(dal: MamsDAL):
    """Create a node that extracts durable memory and closes the MAMS session."""

    def close_session(state: StoryState) -> dict:
        session_id = state["session_id"]

        # End the session in MAMS
        error = state.get("error")
        status = "failed" if error else "completed"
        dal.end_session(session_id, status)

        return {
            "messages": [
                AIMessage(
                    content=(
                        f"[System] Session {session_id} closed with status '{status}'. "
                        f"Turns completed: {state.get('turn_number', 0)}."
                    )
                )
            ],
        }

    return close_session
