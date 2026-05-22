"""LangGraph state definition for one Director loop.

This is EPHEMERAL working memory — it lives for one run only.
Anything that must survive the run goes to MAMS via the DAL.

Design rule: the LangGraph state carries what agents need *during*
the run (context, recent outputs, pending actions).  MAMS carries
everything durable (beliefs, memories, conflicts, audit trail).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


@dataclass
class AgentContext:
    """Hydrated context for one agent during a run."""
    agent_id: int
    agent_name: str
    agent_type: str
    character_id: int | None = None
    character_name: str | None = None
    memories: list[str] = field(default_factory=list)
    beliefs: list[dict] = field(default_factory=list)
    known_events: list[str] = field(default_factory=list)


class StoryState(TypedDict, total=False):
    """Ephemeral state for one Director loop (one LangGraph run).

    LangGraph requires a TypedDict.  Fields marked as required below
    must be set at graph invocation; the rest default to empty/None.
    """
    # ── Session identity (required at invocation) ───────────────────
    world_id: int
    session_id: int
    director_agent_id: int

    # ── Narrative context ───────────────────────────────────────────
    narrative_context: str
    turn_number: int

    # ── Hydrated agent contexts (keyed by agent_id) ─────────────────
    agent_contexts: dict[int, AgentContext]

    # ── Message history (LangGraph's built-in message accumulator) ──
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Director working state ──────────────────────────────────────
    current_plan: str
    active_agent_id: int | None
    pending_events: list[dict]
    pending_beliefs: list[dict]

    # ── Unresolved conflicts surfaced during the run ────────────────
    unresolved_conflicts: list[dict]

    # ── Signals ─────────────────────────────────────────────────────
    should_end: bool
    error: str | None
