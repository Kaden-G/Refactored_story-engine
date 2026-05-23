"""Dataclass models for every MAMS table and composite query result.

These are plain data carriers — no business logic, no ORM magic.
The DAL returns these so the LangGraph layer never sees raw cursor rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


# ── Objective layer ─────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class World:
    world_id: int
    name: str
    description: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Location:
    location_id: int
    world_id: int
    parent_location_id: int | None
    name: str
    location_type: str
    grid_x: int | None
    grid_y: int | None
    grid_z: int | None


@dataclass(frozen=True, slots=True)
class Character:
    character_id: int
    world_id: int
    name: str
    character_type: str
    description: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class RelationshipType:
    relationship_type_id: int
    label: str
    description: str | None


@dataclass(frozen=True, slots=True)
class EventType:
    event_type_id: int
    label: str
    description: str | None


@dataclass(frozen=True, slots=True)
class CharacterRelationship:
    relationship_id: int
    character_id_from: int
    character_id_to: int
    relationship_type_id: int
    intensity: Decimal
    valid_from: datetime
    valid_until: datetime | None


@dataclass(frozen=True, slots=True)
class CharacterLocation:
    char_location_id: int
    character_id: int
    location_id: int
    grid_x: int | None
    grid_y: int | None
    arrived_at: datetime
    departed_at: datetime | None


@dataclass(frozen=True, slots=True)
class Event:
    event_id: int
    world_id: int
    location_id: int | None
    event_type_id: int
    description: str
    occurred_at: datetime
    session_id: int | None


# ── Agent layer ─────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class AgentType:
    agent_type_id: int
    label: str
    description: str | None


@dataclass(frozen=True, slots=True)
class Agent:
    agent_id: int
    world_id: int
    agent_type_id: int
    name: str
    model_name: str | None
    created_at: datetime
    is_active: bool


@dataclass(frozen=True, slots=True)
class AgentCharacter:
    agent_character_id: int
    agent_id: int
    character_id: int
    assigned_at: datetime
    unassigned_at: datetime | None


@dataclass(frozen=True, slots=True)
class Session:
    session_id: int
    world_id: int
    director_agent_id: int
    started_at: datetime
    ended_at: datetime | None
    status: str
    narrative_context: str | None


@dataclass(frozen=True, slots=True)
class AgentSession:
    agent_session_id: int
    agent_id: int
    session_id: int
    role: str
    joined_at: datetime
    left_at: datetime | None


@dataclass(frozen=True, slots=True)
class Decision:
    decision_id: int
    agent_id: int
    session_id: int
    decision_type: str
    description: str
    rationale: str | None
    made_at: datetime


# ── Epistemic layer ─────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Memory:
    memory_id: int
    agent_id: int
    world_id: int
    content: str
    confidence: Decimal
    created_at: datetime
    last_accessed_at: datetime | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class Belief:
    belief_id: int
    agent_id: int
    subject_type: str
    subject_id: int
    belief_content: str
    confidence: Decimal
    created_at: datetime
    superseded_by: int | None


@dataclass(frozen=True, slots=True)
class KnowledgeEvent:
    knowledge_event_id: int
    agent_id: int
    event_id: int
    learned_at: datetime
    learned_via: str


@dataclass(frozen=True, slots=True)
class Conflict:
    conflict_id: int
    belief_id_1: int
    belief_id_2: int
    conflict_type: str
    detected_at: datetime
    resolved_at: datetime | None
    resolution_decision_id: int | None


# ── Composite result types (from functions / queries) ───────────────

@dataclass(frozen=True, slots=True)
class LocationOccupant:
    """Returned by get_location_occupants()."""
    character_id: int
    character_name: str
    arrived_at: datetime


@dataclass(frozen=True, slots=True)
class AgentBeliefResult:
    """Returned by get_agent_belief()."""
    belief_id: int
    belief_content: str
    confidence: Decimal
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UnresolvedConflict:
    """Query 2: unresolved conflicts with agent names and belief text.

    Includes the underlying belief and agent ids so the orchestration
    layer can call resolve_conflict() without re-querying.
    """
    conflict_id: int
    agent_1: str
    agent_id_1: int
    belief_id_1: int
    belief_1: str
    agent_2: str
    agent_id_2: int
    belief_id_2: int
    belief_2: str
    detected_at: datetime


@dataclass(frozen=True, slots=True)
class BeliefDivergence:
    """Query 4: agent belief vs. world divergence report."""
    agent: str
    belief_content: str
    confidence: Decimal
    belief_state: str


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """Query 5: full decision audit trail for a session."""
    made_at: datetime
    decided_by: str
    decision_type: str
    description: str
    rationale: str | None


@dataclass(frozen=True, slots=True)
class RelationshipHistory:
    """Query 6: relationship history between two characters."""
    from_character: str
    to_character: str
    relationship: str
    intensity: Decimal
    valid_from: datetime
    valid_until: str


@dataclass(frozen=True, slots=True)
class EventKnowledgeStatus:
    """Query 7: which agents know about a given event, and which do not."""
    agent: str
    knowledge_status: str


@dataclass(frozen=True, slots=True)
class LocationNode:
    """Query 8: location hierarchy."""
    depth: int
    name: str
    path: str


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Query 10: session summary — events, decisions, conflicts."""
    session_id: int
    status: str
    narrative_context: str | None
    events: int
    decisions: int
    conflicts_involving_session_agents: int
