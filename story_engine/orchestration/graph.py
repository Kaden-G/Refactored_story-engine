"""Director StateGraph — the main orchestration loop.

One invocation of this graph = one MAMS session.

Flow:
  open_session → director_plan → process_events → process_beliefs
       ↑                                              |
       |              ← (loop if not done) ←──────────┘
       |                                              |
       └──────────────── close_session ←──────────────┘
                          (if done)
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from story_engine.dal.mams_dal import MamsDAL
from story_engine.orchestration.nodes import (
    make_close_session_node,
    make_director_plan_node,
    make_open_session_node,
    make_process_beliefs_node,
    make_process_events_node,
)
from story_engine.orchestration.state import StoryState


def _should_continue(state: StoryState) -> str:
    """Routing function: continue the loop or close the session."""
    if state.get("error"):
        return "close_session"
    if state.get("should_end", False):
        return "close_session"
    return "director_plan"


def build_director_graph(
    dal: MamsDAL,
    llm=None,
) -> StateGraph:
    """Build and compile the Director loop graph.

    Parameters
    ----------
    dal : MamsDAL
        The data-access layer instance (backed by a connection pool).
    llm : optional
        A LangChain chat model (e.g. ChatAnthropic).  If *None*, the
        Director uses a rule-based fallback — useful for testing the
        full round-trip without an API key.

    Returns
    -------
    CompiledGraph
        A compiled LangGraph ready to .invoke() or .stream().
    """
    graph = StateGraph(StoryState)

    # ── Register nodes ──────────────────────────────────────────────
    graph.add_node("open_session", make_open_session_node(dal))
    graph.add_node("director_plan", make_director_plan_node(dal, llm))
    graph.add_node("process_events", make_process_events_node(dal))
    graph.add_node("process_beliefs", make_process_beliefs_node(dal))
    graph.add_node("close_session", make_close_session_node(dal))

    # ── Wire edges ──────────────────────────────────────────────────
    graph.set_entry_point("open_session")

    graph.add_edge("open_session", "director_plan")
    graph.add_edge("director_plan", "process_events")
    graph.add_edge("process_events", "process_beliefs")

    # After processing beliefs, decide: loop or close
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
