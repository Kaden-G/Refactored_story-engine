"""Director StateGraph — the main orchestration loop.

One invocation of this graph = one MAMS session.

Flow:
  open_session
       │
       ▼
  director_plan ──→ route_agent ──→ writer_act ─────┐
       ▲                       ├──→ lorekeeper_act ──┤
       │                       └──→ npc_act ─────────┤
       │                                             ▼
       │                                      process_events
       │                                             │
       │                                             ▼
       │                                      process_beliefs
       │                                             │
       └──── (loop if not done) ─────────────────────┘
                                                     │
                                              close_session ──→ END
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from story_engine.dal.mams_dal import MamsDAL
from story_engine.orchestration.nodes import (
    make_close_session_node,
    make_director_plan_node,
    make_lorekeeper_node,
    make_npc_node,
    make_open_session_node,
    make_process_beliefs_node,
    make_process_events_node,
    make_writer_node,
)
from story_engine.orchestration.state import StoryState


def _route_agent(state: StoryState) -> str:
    """After director_plan, route to the appropriate agent node."""
    if state.get("error"):
        return "close_session"
    if state.get("should_end", False):
        return "close_session"

    active_id = state.get("active_agent_id")
    contexts = state.get("agent_contexts", {})
    plan = state.get("current_plan", "").lower()

    # If Director explicitly named "writer" or it's a scene-setting turn
    if "writer" in plan:
        return "writer_act"

    # If there's an active agent, check its type
    if active_id and active_id in contexts:
        ctx = contexts[active_id]
        if "lore" in ctx.agent_name.lower():
            return "lorekeeper_act"
        if ctx.character_id is not None:
            return "npc_act"

    # Fallback: if plan mentions lore/conflict, route to lore-keeper
    if "conflict" in plan or "lore" in plan:
        return "lorekeeper_act"

    # Default: writer for narrative, or npc if an agent is selected
    if active_id:
        return "npc_act"
    return "writer_act"


def _should_continue(state: StoryState) -> str:
    """After process_beliefs, decide: loop back to director or close."""
    if state.get("error"):
        return "close_session"
    if state.get("should_end", False):
        return "close_session"
    return "director_plan"


def build_director_graph(
    dal: MamsDAL,
    llm=None,
    max_turns: int = 5,
) -> StateGraph:
    """Build and compile the Director loop graph.

    Parameters
    ----------
    dal : MamsDAL
        The data-access layer instance (backed by a connection pool).
    llm : optional
        A LangChain chat model (e.g. ChatAnthropic).  If *None*, all
        agents use rule-based fallbacks — useful for testing the full
        round-trip without an API key.
    max_turns : int
        Maximum Director turns before the session auto-closes.

    Returns
    -------
    CompiledGraph
        A compiled LangGraph ready to .invoke() or .stream().
    """
    graph = StateGraph(StoryState)

    # ── Register nodes ──────────────────────────────────────────────
    graph.add_node("open_session", make_open_session_node(dal))
    graph.add_node("director_plan", make_director_plan_node(dal, llm, max_turns))
    graph.add_node("writer_act", make_writer_node(dal, llm))
    graph.add_node("lorekeeper_act", make_lorekeeper_node(dal, llm))
    graph.add_node("npc_act", make_npc_node(dal, llm))
    graph.add_node("process_events", make_process_events_node(dal))
    graph.add_node("process_beliefs", make_process_beliefs_node(dal))
    graph.add_node("close_session", make_close_session_node(dal))

    # ── Wire edges ──────────────────────────────────────────────────
    graph.set_entry_point("open_session")

    # open → director plans the turn
    graph.add_edge("open_session", "director_plan")

    # director → route to the right agent
    graph.add_conditional_edges(
        "director_plan",
        _route_agent,
        {
            "writer_act": "writer_act",
            "lorekeeper_act": "lorekeeper_act",
            "npc_act": "npc_act",
            "close_session": "close_session",
        },
    )

    # all agent nodes → process_events → process_beliefs
    graph.add_edge("writer_act", "process_events")
    graph.add_edge("lorekeeper_act", "process_events")
    graph.add_edge("npc_act", "process_events")
    graph.add_edge("process_events", "process_beliefs")

    # after processing, loop or close
    graph.add_conditional_edges(
        "process_beliefs",
        _should_continue,
        {
            "director_plan": "director_plan",
            "close_session": "close_session",
        },
    )

    graph.add_edge("close_session", END)

    return graph.compile()
