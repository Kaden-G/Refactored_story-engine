"""Pydantic response models for the story-engine API."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


# ── World & entities ────────────────────────────────────────────────

class WorldOut(BaseModel):
    world_id: int
    name: str
    description: str | None = None
    created_at: datetime | None = None

class CharacterOut(BaseModel):
    character_id: int
    name: str
    description: str | None = None
    world_id: int

class LocationOut(BaseModel):
    location_id: int
    name: str
    location_type: str
    parent_location_id: int | None = None
    world_id: int

class AgentOut(BaseModel):
    agent_id: int
    name: str
    agent_type_id: int
    is_active: bool = True


# ── Session ─────────────────────────────────────────────────────────

class SessionStartRequest(BaseModel):
    world_id: int
    director_agent_id: int
    narrative_context: str = ""
    max_turns: int = 5

class SessionOut(BaseModel):
    session_id: int
    world_id: int
    status: str
    turn_number: int
    narrative_context: str = ""

class TurnResult(BaseModel):
    turn_number: int
    messages: list[MessageOut]
    should_end: bool
    unresolved_conflicts: int = 0
    active_agent: str | None = None

class MessageOut(BaseModel):
    role: str
    agent_name: str | None = None
    content: str


# ── Agent context (for state inspector) ─────────────────────────────

class AgentContextOut(BaseModel):
    agent_id: int
    agent_name: str
    agent_type: str
    character_name: str | None = None
    memory_count: int = 0
    belief_count: int = 0
    event_count: int = 0

class BeliefOut(BaseModel):
    belief_id: int
    agent_id: int
    subject_type: str
    subject_id: int
    belief_content: str
    confidence: float

class ConflictOut(BaseModel):
    conflict_id: int
    agent_1: str
    belief_1: str
    agent_2: str
    belief_2: str

class MemoryOut(BaseModel):
    memory_id: int
    agent_id: int
    content: str
    confidence: float


# ── SSE event types ─────────────────────────────────────────────────

class SSEMessage(BaseModel):
    """Shape of each SSE data payload."""
    event_type: str          # "message", "turn_start", "turn_end", "session_end", "error"
    turn_number: int | None = None
    role: str | None = None
    agent_name: str | None = None
    content: str = ""
    should_end: bool = False
