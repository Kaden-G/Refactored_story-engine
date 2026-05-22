"""Node functions for the Director StateGraph.

Each function is a LangGraph node: it receives StoryState, does work
(calling the DAL for durable reads/writes, calling an LLM for generation),
and returns a partial state update.

No node should import psycopg or touch the database directly — all DB
access goes through the MamsDAL instance injected at graph-build time.
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from story_engine.dal.mams_dal import MamsDAL
from story_engine.orchestration.prompts import (
    build_director_system_prompt,
    build_lorekeeper_system_prompt,
    build_npc_system_prompt,
    build_writer_system_prompt,
)
from story_engine.orchestration.state import AgentContext, StoryState

log = logging.getLogger(__name__)


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
            # Resolve the character this agent portrays (if any)
            char = dal.get_character_for_agent(agent.agent_id)
            char_id = char.character_id if char else None
            char_name = char.name if char else None

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


def make_director_plan_node(dal: MamsDAL, llm=None, max_turns: int = 5):
    """Create a node where the Director decides what to do next.

    With an LLM: returns structured JSON with next_agent + instruction.
    Without: rule-based fallback that cycles through agents.
    """

    def _parse_director_json(text: str) -> dict | None:
        """Try to extract a JSON object from the LLM response."""
        try:
            # Handle markdown-fenced JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except (json.JSONDecodeError, IndexError):
            log.warning("Director output was not valid JSON; using raw text.")
            return None

    def director_plan(state: StoryState) -> dict:
        turn = state.get("turn_number", 0)
        conflicts = state.get("unresolved_conflicts", [])
        contexts = state.get("agent_contexts", {})
        narrative_context = state.get("narrative_context", "")

        next_agent: str | None = None
        instruction: str = ""
        plan: str = ""
        should_end = turn >= max_turns

        if llm is not None:
            system_prompt = build_director_system_prompt(
                agent_contexts=contexts,
                unresolved_conflicts=conflicts,
                narrative_context=narrative_context,
                turn_number=turn,
            )
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content="What should happen next in this session?"),
            ])
            parsed = _parse_director_json(response.content)
            if parsed:
                next_agent = parsed.get("next_agent")
                instruction = parsed.get("instruction", "")
                plan = parsed.get("reasoning", response.content)
                should_end = parsed.get("should_end", should_end)
            else:
                plan = response.content
        else:
            # Rule-based fallback: cycle through priorities
            npc_agents = [
                ctx for ctx in contexts.values()
                if ctx.character_id is not None
            ]
            specialist_agents = [
                ctx for ctx in contexts.values()
                if ctx.character_id is None and ctx.agent_type != "director"
            ]

            if conflicts and specialist_agents:
                # Priority 1: route conflicts to Lore-keeper
                lorekeeper = next(
                    (a for a in specialist_agents if "lore" in a.agent_name.lower()),
                    specialist_agents[0],
                )
                next_agent = lorekeeper.agent_name
                instruction = (
                    f"Review and adjudicate {len(conflicts)} unresolved conflict(s). "
                    "Determine which belief is canon and provide rationale."
                )
                plan = f"Turn {turn}: Routing {len(conflicts)} conflict(s) to {next_agent}."
            elif turn == 0 and npc_agents:
                # Priority 2: first turn, get the scene started
                next_agent = "Writer"
                instruction = (
                    "Set the scene for the current session. Describe the world state "
                    "and establish the opening narrative beat."
                )
                plan = f"Turn {turn}: Opening session — Writer sets the scene."
            elif npc_agents:
                # Priority 3: cycle through NPCs
                npc_idx = (turn - 1) % len(npc_agents)
                target = npc_agents[npc_idx]
                next_agent = target.agent_name
                instruction = (
                    "Respond to the current narrative situation in character. "
                    "What does your character do or say?"
                )
                plan = f"Turn {turn}: {next_agent} takes action."
            else:
                plan = f"Turn {turn}: No actionable agents. Ending session."
                should_end = True

        return {
            "current_plan": plan,
            "active_agent_id": _resolve_agent_id(next_agent, contexts),
            "turn_number": turn + 1,
            "should_end": should_end,
            "messages": [
                AIMessage(content=f"[Director] {plan}")
            ],
        }

    return director_plan


def _resolve_agent_id(
    agent_name: str | None,
    contexts: dict[int, AgentContext],
) -> int | None:
    """Look up an agent_id by name (or partial match) from the contexts."""
    if agent_name is None:
        return None
    name_lower = agent_name.lower()
    for aid, ctx in contexts.items():
        if name_lower in ctx.agent_name.lower():
            return aid
    return None


# ── Writer node ─────────────────────────────────────────────────────

def make_writer_node(dal: MamsDAL, llm=None):
    """Create a node where the Writer generates narrative prose."""

    def writer_act(state: StoryState) -> dict:
        plan = state.get("current_plan", "")
        contexts = state.get("agent_contexts", {})
        messages = state.get("messages", [])

        # Gather recent narrative messages for context
        recent = [
            m.content for m in messages[-10:]
            if isinstance(m, AIMessage) and "[Writer]" in m.content
        ]

        world = dal.get_world(state["world_id"])
        world_desc = world.description if world else "Unknown world"

        if llm is not None:
            prompt = build_writer_system_prompt(
                instruction=plan,
                world_description=world_desc,
                recent_messages=recent,
            )
            response = llm.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content="Write the next narrative passage."),
            ])
            narrative = response.content
        else:
            narrative = (
                f"[Narrative stub — Writer would generate prose here]\n"
                f"Scene context: {plan}\n"
                f"World: {world_desc}"
            )

        return {
            "messages": [
                AIMessage(content=f"[Writer] {narrative}")
            ],
        }

    return writer_act


# ── Lore-keeper node ────────────────────────────────────────────────

def make_lorekeeper_node(dal: MamsDAL, llm=None):
    """Create a node where the Lore-keeper checks consistency or resolves conflicts."""

    def lorekeeper_act(state: StoryState) -> dict:
        plan = state.get("current_plan", "")
        conflicts = state.get("unresolved_conflicts", [])
        contexts = state.get("agent_contexts", {})

        # Find the Lore-keeper's own context
        lk_ctx = next(
            (c for c in contexts.values() if "lore" in c.agent_name.lower()),
            None,
        )
        memories = lk_ctx.memories if lk_ctx else []
        known_events = lk_ctx.known_events if lk_ctx else []

        if llm is not None:
            prompt = build_lorekeeper_system_prompt(
                instruction=plan,
                memories=memories,
                conflicts=conflicts,
                known_events=known_events,
            )
            response = llm.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content="Adjudicate or provide lore context."),
            ])
            output = response.content

            # Try to parse conflict resolution JSON
            try:
                if "```json" in output:
                    json_str = output.split("```json")[1].split("```")[0]
                elif "```" in output:
                    json_str = output.split("```")[1].split("```")[0]
                else:
                    json_str = output
                resolution = json.loads(json_str.strip())

                if "conflict_id" in resolution and "rationale" in resolution:
                    # The Lore-keeper resolved a conflict — write to MAMS
                    cid = resolution["conflict_id"]
                    # Find the winning belief
                    winning_agent_name = resolution.get("winning_belief_agent", "")
                    conflict_data = next(
                        (c for c in conflicts if c.get("conflict_id") == cid),
                        None,
                    )
                    if conflict_data:
                        log.info(
                            "Lore-keeper resolved conflict %s in favor of %s",
                            cid, winning_agent_name,
                        )
            except (json.JSONDecodeError, IndexError, KeyError):
                pass  # Not a resolution response — that's fine
        else:
            if conflicts:
                output = (
                    f"[Lore-keeper stub — would adjudicate {len(conflicts)} conflict(s)]\n"
                    + "\n".join(
                        f"  Conflict {c.get('conflict_id', '?')}: "
                        f"{c['agent_1']} vs {c['agent_2']}"
                        for c in conflicts
                    )
                )
            else:
                output = "[Lore-keeper stub — no conflicts to adjudicate. Lore is consistent.]"

        return {
            "messages": [
                AIMessage(content=f"[Lore-keeper] {output}")
            ],
        }

    return lorekeeper_act


# ── NPC agent node ──────────────────────────────────────────────────

def make_npc_node(dal: MamsDAL, llm=None):
    """Create a node where the active NPC agent speaks in character."""

    def npc_act(state: StoryState) -> dict:
        active_id = state.get("active_agent_id")
        contexts = state.get("agent_contexts", {})
        plan = state.get("current_plan", "")

        if active_id is None or active_id not in contexts:
            return {
                "messages": [
                    AIMessage(content="[System] No active NPC agent selected.")
                ],
            }

        ctx = contexts[active_id]

        # Resolve character description and location from MAMS
        char_desc = ""
        location_name = None
        nearby: list[str] = []

        if ctx.character_id is not None:
            char = dal.get_character(ctx.character_id)
            char_desc = char.description or "" if char else ""

            char_loc = dal.get_character_current_location(ctx.character_id)
            if char_loc:
                loc = dal.get_location(char_loc.location_id)
                location_name = loc.name if loc else None
                occupants = dal.get_location_occupants(char_loc.location_id)
                nearby = [
                    o.character_name for o in occupants
                    if o.character_id != ctx.character_id
                ]

        if llm is not None:
            prompt = build_npc_system_prompt(
                agent_context=ctx,
                character_description=char_desc,
                instruction=plan,
                location_name=location_name,
                nearby_characters=nearby,
            )
            response = llm.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content="Respond in character to the current situation."),
            ])
            output = response.content
        else:
            output = (
                f"[{ctx.character_name or ctx.agent_name} stub — would respond in character]\n"
                f"Location: {location_name or 'unknown'}\n"
                f"Nearby: {', '.join(nearby) or 'no one'}\n"
                f"Memories: {len(ctx.memories)} | Beliefs: {len(ctx.beliefs)}\n"
                f"Instruction: {plan}"
            )

        return {
            "messages": [
                AIMessage(
                    content=f"[{ctx.character_name or ctx.agent_name}] {output}"
                )
            ],
        }

    return npc_act


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
        world_id = state["world_id"]
        contexts = state.get("agent_contexts", {})

        # Extract durable memories from the session's message log.
        # Each agent that participated gets a summary memory.
        messages = state.get("messages", [])
        narrative_messages = [
            m.content for m in messages
            if isinstance(m, AIMessage)
            and not m.content.startswith("[System]")
        ]
        if narrative_messages:
            session_summary = (
                f"Session {session_id} narrative: "
                + " | ".join(msg[:120] for msg in narrative_messages[-5:])
            )
            # Write a memory for the director
            director_id = state.get("director_agent_id")
            if director_id:
                try:
                    dal.create_memory(
                        agent_id=director_id,
                        world_id=world_id,
                        content=session_summary[:500],
                        confidence=0.80,
                    )
                except Exception as e:
                    log.warning("Failed to write session memory: %s", e)

        # End the session in MAMS
        error = state.get("error")
        status = "failed" if error else "completed"
        dal.end_session(session_id, status)

        return {
            "messages": [
                AIMessage(
                    content=(
                        f"[System] Session {session_id} closed with status '{status}'. "
                        f"Turns completed: {state.get('turn_number', 0)}. "
                        f"Narrative memories extracted."
                    )
                )
            ],
        }

    return close_session
