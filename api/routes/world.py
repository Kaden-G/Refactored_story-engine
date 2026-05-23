"""World and entity query routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.schemas import (
    AgentContextOut,
    AgentOut,
    BeliefOut,
    CharacterOut,
    ConflictOut,
    LocationOut,
    MemoryOut,
    WorldOut,
)

router = APIRouter()


def _dal(request: Request):
    return request.app.state.dal


# ── Worlds ──────────────────────────────────────────────────────────

@router.get("/worlds", response_model=list[WorldOut])
def list_worlds(request: Request):
    dal = _dal(request)
    worlds = dal.get_worlds()
    return [
        WorldOut(
            world_id=w.world_id,
            name=w.name,
            description=w.description,
            created_at=w.created_at,
        )
        for w in worlds
    ]


@router.get("/worlds/{world_id}", response_model=WorldOut)
def get_world(world_id: int, request: Request):
    dal = _dal(request)
    w = dal.get_world(world_id)
    if w is None:
        from fastapi import HTTPException
        raise HTTPException(404, "World not found")
    return WorldOut(
        world_id=w.world_id,
        name=w.name,
        description=w.description,
        created_at=w.created_at,
    )


# ── Characters ──────────────────────────────────────────────────────

@router.get("/worlds/{world_id}/characters", response_model=list[CharacterOut])
def list_characters(world_id: int, request: Request):
    dal = _dal(request)
    chars = dal.get_characters(world_id)
    return [
        CharacterOut(
            character_id=c.character_id,
            name=c.name,
            description=c.description,
            world_id=c.world_id,
        )
        for c in chars
    ]


# ── Locations ───────────────────────────────────────────────────────

@router.get("/worlds/{world_id}/locations", response_model=list[LocationOut])
def list_locations(world_id: int, request: Request):
    dal = _dal(request)
    locs = dal.get_locations(world_id)
    return [
        LocationOut(
            location_id=loc.location_id,
            name=loc.name,
            location_type=loc.location_type,
            parent_location_id=loc.parent_location_id,
            world_id=loc.world_id,
        )
        for loc in locs
    ]


# ── Agents ──────────────────────────────────────────────────────────

@router.get("/worlds/{world_id}/agents", response_model=list[AgentOut])
def list_agents(world_id: int, request: Request):
    dal = _dal(request)
    agents = dal.get_agents(world_id)
    return [
        AgentOut(
            agent_id=a.agent_id,
            name=a.name,
            agent_type_id=a.agent_type_id,
            is_active=a.is_active,
        )
        for a in agents
    ]


# ── Agent state (beliefs, memories, conflicts) ──────────────────────

@router.get("/agents/{agent_id}/beliefs", response_model=list[BeliefOut])
def get_agent_beliefs(agent_id: int, request: Request):
    dal = _dal(request)
    beliefs = dal.get_beliefs_for_agent(agent_id)
    return [
        BeliefOut(
            belief_id=b.belief_id,
            agent_id=b.agent_id,
            subject_type=b.subject_type,
            subject_id=b.subject_id,
            belief_content=b.belief_content,
            confidence=float(b.confidence),
        )
        for b in beliefs
    ]


@router.get("/agents/{agent_id}/memories", response_model=list[MemoryOut])
def get_agent_memories(agent_id: int, request: Request):
    dal = _dal(request)
    memories = dal.get_agent_memories(agent_id)
    return [
        MemoryOut(
            memory_id=m.memory_id,
            agent_id=m.agent_id,
            content=m.content,
            confidence=float(m.confidence),
        )
        for m in memories
    ]


@router.get("/conflicts", response_model=list[ConflictOut])
def get_unresolved_conflicts(request: Request):
    dal = _dal(request)
    conflicts = dal.get_unresolved_conflicts()
    return [
        ConflictOut(
            conflict_id=c.conflict_id,
            agent_1=c.agent_1,
            belief_1=c.belief_1,
            agent_2=c.agent_2,
            belief_2=c.belief_2,
        )
        for c in conflicts
    ]
