"""MAMS Data-Access Layer — one Python function per database operation.

Design contract:
- Parameterized queries only (no string formatting).
- Returns dataclasses, never raw cursor rows.
- Contains NO narrative or orchestration logic.
- Each public method maps to a MAMS procedure, function, or query.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from story_engine.dal.models import (
    Agent,
    AgentBeliefResult,
    AgentSession,
    Belief,
    BeliefDivergence,
    Character,
    CharacterLocation,
    CharacterRelationship,
    Conflict,
    Decision,
    DecisionRecord,
    Event,
    EventKnowledgeStatus,
    EventType,
    KnowledgeEvent,
    Location,
    LocationNode,
    LocationOccupant,
    Memory,
    RelationshipHistory,
    RelationshipType,
    Session,
    SessionSummary,
    UnresolvedConflict,
    World,
)


class MamsDAL:
    """Thin bridge between Python and the MAMS PostgreSQL database."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    # ── helpers ──────────────────────────────────────────────────────

    def _fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    # ── Stored procedures (multi-step writes) ────────────────────────

    def start_session(
        self,
        world_id: int,
        director_agent_id: int,
        narrative_context: str,
    ) -> int:
        """Open a new Director session and enroll all active agents.

        Returns the new session_id.
        """
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "CALL start_session(%(world_id)s, %(director)s, "
                    "%(context)s, %(session_id)s)",
                    {
                        "world_id": world_id,
                        "director": director_agent_id,
                        "context": narrative_context,
                        "session_id": None,
                    },
                )
                row = cur.fetchone()
                return row["p_session_id"]

    def propagate_event(self, event_id: int) -> None:
        """Distribute event knowledge to agents whose character was present."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CALL propagate_event(%s)", (event_id,))

    def resolve_conflict(
        self,
        conflict_id: int,
        winning_belief_id: int,
        resolving_agent_id: int,
        rationale: str,
    ) -> None:
        """Resolve a conflict: supersede the losing belief, log a decision."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "CALL resolve_conflict(%s, %s, %s, %s)",
                    (conflict_id, winning_belief_id,
                     resolving_agent_id, rationale),
                )

    # ── SQL functions (read-only) ────────────────────────────────────

    def get_conflict_count(self, agent_id: int) -> int:
        """Return the number of unresolved conflicts involving an agent."""
        row = self._fetchone(
            "SELECT get_conflict_count(%s) AS cnt", (agent_id,)
        )
        return row["cnt"] if row else 0

    def get_location_occupants(
        self,
        location_id: int,
        at_time: datetime | None = None,
    ) -> list[LocationOccupant]:
        """Return characters present at a location at a given time."""
        if at_time is None:
            rows = self._fetchall(
                "SELECT * FROM get_location_occupants(%s)", (location_id,)
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM get_location_occupants(%s, %s)",
                (location_id, at_time),
            )
        return [LocationOccupant(**r) for r in rows]

    def get_agent_belief(
        self,
        agent_id: int,
        subject_type: str,
        subject_id: int,
    ) -> list[AgentBeliefResult]:
        """Return an agent's current (non-superseded) beliefs about a subject."""
        rows = self._fetchall(
            "SELECT * FROM get_agent_belief(%s, %s, %s)",
            (agent_id, subject_type, subject_id),
        )
        return [AgentBeliefResult(**r) for r in rows]

    # ── Write helpers (single-row inserts for the LangGraph layer) ──

    def create_event(
        self,
        world_id: int,
        location_id: int | None,
        event_type_id: int,
        description: str,
        session_id: int | None = None,
        occurred_at: datetime | None = None,
    ) -> int:
        """Insert a new event and return its event_id."""
        sql = (
            "INSERT INTO event "
            "(world_id, location_id, event_type_id, description, session_id"
            + (", occurred_at" if occurred_at else "")
            + ") VALUES (%s, %s, %s, %s, %s"
            + (", %s" if occurred_at else "")
            + ") RETURNING event_id"
        )
        params: tuple = (
            world_id, location_id, event_type_id, description, session_id,
        )
        if occurred_at:
            params = params + (occurred_at,)
        row = self._fetchone(sql, params)
        return row["event_id"]

    def create_belief(
        self,
        agent_id: int,
        subject_type: str,
        subject_id: int,
        belief_content: str,
        confidence: Decimal | float = 1.0,
    ) -> int:
        """Insert a new belief and return its belief_id.

        The trg_detect_conflict trigger fires automatically on INSERT.
        """
        row = self._fetchone(
            "INSERT INTO belief "
            "(agent_id, subject_type, subject_id, belief_content, confidence) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING belief_id",
            (agent_id, subject_type, subject_id, belief_content,
             Decimal(str(confidence))),
        )
        return row["belief_id"]

    def create_memory(
        self,
        agent_id: int,
        world_id: int,
        content: str,
        confidence: Decimal | float = 1.0,
    ) -> int:
        """Insert a durable memory for an agent and return memory_id."""
        row = self._fetchone(
            "INSERT INTO memory (agent_id, world_id, content, confidence) "
            "VALUES (%s, %s, %s, %s) RETURNING memory_id",
            (agent_id, world_id, content, Decimal(str(confidence))),
        )
        return row["memory_id"]

    def create_decision(
        self,
        agent_id: int,
        session_id: int,
        decision_type: str,
        description: str,
        rationale: str | None = None,
    ) -> int:
        """Log an agent decision and return decision_id."""
        row = self._fetchone(
            "INSERT INTO decision "
            "(agent_id, session_id, decision_type, description, rationale) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING decision_id",
            (agent_id, session_id, decision_type, description, rationale),
        )
        return row["decision_id"]

    def create_knowledge_event(
        self,
        agent_id: int,
        event_id: int,
        learned_via: str = "direct",
    ) -> int:
        """Record that an agent learned about an event. Returns knowledge_event_id."""
        row = self._fetchone(
            "INSERT INTO knowledge_event (agent_id, event_id, learned_via) "
            "VALUES (%s, %s, %s) RETURNING knowledge_event_id",
            (agent_id, event_id, learned_via),
        )
        return row["knowledge_event_id"]

    def move_character(
        self,
        character_id: int,
        new_location_id: int,
        grid_x: int | None = None,
        grid_y: int | None = None,
    ) -> int:
        """Depart from current location (if any) and arrive at a new one.

        Returns the new char_location_id.
        """
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # close the current location record
                cur.execute(
                    "UPDATE character_location "
                    "SET departed_at = now() "
                    "WHERE character_id = %s AND departed_at IS NULL",
                    (character_id,),
                )
                # insert the new location record
                cur.execute(
                    "INSERT INTO character_location "
                    "(character_id, location_id, grid_x, grid_y) "
                    "VALUES (%s, %s, %s, %s) RETURNING char_location_id",
                    (character_id, new_location_id, grid_x, grid_y),
                )
                row = cur.fetchone()
                return row["char_location_id"]

    def end_session(self, session_id: int, status: str = "completed") -> None:
        """Mark a session as completed (or failed). Trigger auto-stamps ended_at."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE session SET status = %s WHERE session_id = %s",
                    (status, session_id),
                )

    def deactivate_memory(self, memory_id: int) -> None:
        """Soft-delete a memory by setting is_active = FALSE."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE memory SET is_active = FALSE WHERE memory_id = %s",
                    (memory_id,),
                )

    # ── Read queries (the 10 from 08_queries.sql, plus extras) ──────

    def get_agent_memories(
        self, agent_id: int, active_only: bool = True,
    ) -> list[Memory]:
        """Query 1: all memories for a given agent, newest first."""
        sql = (
            "SELECT * FROM memory "
            "WHERE agent_id = %s"
            + (" AND is_active = TRUE" if active_only else "")
            + " ORDER BY created_at DESC"
        )
        return [Memory(**r) for r in self._fetchall(sql, (agent_id,))]

    def get_unresolved_conflicts(self) -> list[UnresolvedConflict]:
        """Query 2: all unresolved conflicts with agent names and belief text."""
        rows = self._fetchall(
            "SELECT c.conflict_id, "
            "       a1.name AS agent_1, b1.belief_content AS belief_1, "
            "       a2.name AS agent_2, b2.belief_content AS belief_2, "
            "       c.detected_at "
            "  FROM conflict c "
            "  JOIN belief b1 ON c.belief_id_1 = b1.belief_id "
            "  JOIN belief b2 ON c.belief_id_2 = b2.belief_id "
            "  JOIN agent  a1 ON b1.agent_id   = a1.agent_id "
            "  JOIN agent  a2 ON b2.agent_id   = a2.agent_id "
            " WHERE c.resolved_at IS NULL "
            " ORDER BY c.conflict_id"
        )
        return [UnresolvedConflict(**r) for r in rows]

    def get_characters_at_event_location(
        self, event_id: int,
    ) -> list[LocationOccupant]:
        """Query 3: characters present at a location during an event."""
        rows = self._fetchall(
            "SELECT ch.character_id, "
            "       ch.name AS character_name, "
            "       cl.arrived_at "
            "  FROM event e "
            "  JOIN character_location cl "
            "    ON cl.location_id = e.location_id "
            "   AND cl.arrived_at <= e.occurred_at "
            "   AND (cl.departed_at IS NULL OR cl.departed_at > e.occurred_at) "
            "  JOIN character ch ON cl.character_id = ch.character_id "
            " WHERE e.event_id = %s "
            " ORDER BY ch.name",
            (event_id,),
        )
        return [LocationOccupant(**r) for r in rows]

    def get_belief_divergence(
        self, subject_type: str, subject_id: int,
    ) -> list[BeliefDivergence]:
        """Query 4: agent belief divergence report for a subject."""
        rows = self._fetchall(
            "SELECT a.name AS agent, "
            "       b.belief_content, "
            "       b.confidence, "
            "       CASE WHEN b.superseded_by IS NULL "
            "            THEN 'current' ELSE 'superseded' END AS belief_state "
            "  FROM belief b "
            "  JOIN agent a ON b.agent_id = a.agent_id "
            " WHERE b.subject_type = %s "
            "   AND b.subject_id   = %s "
            " ORDER BY b.confidence DESC",
            (subject_type, subject_id),
        )
        return [BeliefDivergence(**r) for r in rows]

    def get_session_decisions(self, session_id: int) -> list[DecisionRecord]:
        """Query 5: full decision audit trail for a session."""
        rows = self._fetchall(
            "SELECT d.made_at, "
            "       a.name AS decided_by, "
            "       d.decision_type, "
            "       d.description, "
            "       d.rationale "
            "  FROM decision d "
            "  JOIN agent   a ON d.agent_id   = a.agent_id "
            " WHERE d.session_id = %s "
            " ORDER BY d.made_at",
            (session_id,),
        )
        return [DecisionRecord(**r) for r in rows]

    def get_relationship_history(
        self, character_name_1: str, character_name_2: str,
    ) -> list[RelationshipHistory]:
        """Query 6: relationship history between two characters (by name)."""
        rows = self._fetchall(
            "SELECT cf.name AS from_character, "
            "       ct.name AS to_character, "
            "       rt.label AS relationship, "
            "       cr.intensity, "
            "       cr.valid_from, "
            "       COALESCE(cr.valid_until::text, 'still in effect') "
            "           AS valid_until "
            "  FROM character_relationship cr "
            "  JOIN character cf ON cr.character_id_from = cf.character_id "
            "  JOIN character ct ON cr.character_id_to   = ct.character_id "
            "  JOIN relationship_type rt "
            "    ON cr.relationship_type_id = rt.relationship_type_id "
            " WHERE (cf.name = %s AND ct.name = %s) "
            "    OR (cf.name = %s AND ct.name = %s) "
            " ORDER BY cr.valid_from",
            (character_name_1, character_name_2,
             character_name_2, character_name_1),
        )
        return [RelationshipHistory(**r) for r in rows]

    def get_event_knowledge_status(
        self, event_id: int,
    ) -> list[EventKnowledgeStatus]:
        """Query 7: which NPC agents know about a given event."""
        rows = self._fetchall(
            "SELECT a.name AS agent, "
            "       CASE WHEN ke.knowledge_event_id IS NULL "
            "            THEN 'does NOT know' "
            "            ELSE 'knows (via ' || ke.learned_via || ')' "
            "       END AS knowledge_status "
            "  FROM agent a "
            "  LEFT JOIN knowledge_event ke "
            "    ON ke.agent_id = a.agent_id "
            "   AND ke.event_id = %s "
            " WHERE a.agent_type_id = "
            "       (SELECT agent_type_id FROM agent_type "
            "         WHERE label = 'NPC') "
            " ORDER BY knowledge_status, a.name",
            (event_id,),
        )
        return [EventKnowledgeStatus(**r) for r in rows]

    def get_location_hierarchy(
        self, world_id: int | None = None,
    ) -> list[LocationNode]:
        """Query 8: recursive location hierarchy."""
        if world_id is not None:
            world_filter = "AND l_root.world_id = %s"
            params: tuple = (world_id,)
        else:
            world_filter = ""
            params = ()
        rows = self._fetchall(
            "WITH RECURSIVE loc_tree AS ( "
            "    SELECT location_id, name, parent_location_id, 1 AS depth, "
            "           name::text AS path "
            "      FROM location l_root "
            "     WHERE parent_location_id IS NULL "
            f"          {world_filter} "
            "    UNION ALL "
            "    SELECT l.location_id, l.name, l.parent_location_id, "
            "           lt.depth + 1, lt.path || ' > ' || l.name "
            "      FROM location l "
            "      JOIN loc_tree lt ON l.parent_location_id = lt.location_id "
            ") "
            "SELECT depth, name, path FROM loc_tree ORDER BY path",
            params,
        )
        return [LocationNode(**r) for r in rows]

    def get_conflict_counts_by_agent(self) -> list[dict]:
        """Query 9: conflict count per NPC agent."""
        return self._fetchall(
            "SELECT a.name AS agent, "
            "       get_conflict_count(a.agent_id) AS unresolved_conflicts "
            "  FROM agent a "
            " WHERE a.agent_type_id = "
            "       (SELECT agent_type_id FROM agent_type "
            "         WHERE label = 'NPC') "
            " ORDER BY unresolved_conflicts DESC, a.name"
        )

    def get_session_summary(self, session_id: int) -> SessionSummary | None:
        """Query 10: session summary — events, decisions, conflicts."""
        row = self._fetchone(
            "SELECT s.session_id, s.status, s.narrative_context, "
            "       (SELECT count(*) FROM event e "
            "         WHERE e.session_id = s.session_id) AS events, "
            "       (SELECT count(*) FROM decision d "
            "         WHERE d.session_id = s.session_id) AS decisions, "
            "       (SELECT count(*) FROM conflict c "
            "          JOIN belief b ON c.belief_id_1 = b.belief_id "
            "         WHERE b.agent_id IN "
            "               (SELECT agent_id FROM agent_session "
            "                 WHERE session_id = s.session_id) "
            "       ) AS conflicts_involving_session_agents "
            "  FROM session s "
            " WHERE s.session_id = %s",
            (session_id,),
        )
        return SessionSummary(**row) if row else None

    # ── Lookup / entity reads ────────────────────────────────────────

    def get_world(self, world_id: int) -> World | None:
        row = self._fetchone(
            "SELECT * FROM world WHERE world_id = %s", (world_id,)
        )
        return World(**row) if row else None

    def get_world_by_name(self, name: str) -> World | None:
        row = self._fetchone(
            "SELECT * FROM world WHERE name = %s", (name,)
        )
        return World(**row) if row else None

    def get_agents(
        self, world_id: int, active_only: bool = True,
    ) -> list[Agent]:
        sql = (
            "SELECT * FROM agent WHERE world_id = %s"
            + (" AND is_active = TRUE" if active_only else "")
            + " ORDER BY agent_id"
        )
        return [Agent(**r) for r in self._fetchall(sql, (world_id,))]

    def get_agent(self, agent_id: int) -> Agent | None:
        row = self._fetchone(
            "SELECT * FROM agent WHERE agent_id = %s", (agent_id,)
        )
        return Agent(**row) if row else None

    def get_agent_by_name(self, name: str) -> Agent | None:
        row = self._fetchone(
            "SELECT * FROM agent WHERE name = %s", (name,)
        )
        return Agent(**row) if row else None

    def get_characters(
        self, world_id: int, active_only: bool = True,
    ) -> list[Character]:
        sql = (
            "SELECT * FROM character WHERE world_id = %s"
            + (" AND is_active = TRUE" if active_only else "")
            + " ORDER BY character_id"
        )
        return [Character(**r) for r in self._fetchall(sql, (world_id,))]

    def get_character(self, character_id: int) -> Character | None:
        row = self._fetchone(
            "SELECT * FROM character WHERE character_id = %s",
            (character_id,),
        )
        return Character(**row) if row else None

    def get_character_by_name(
        self, name: str, world_id: int | None = None,
    ) -> Character | None:
        if world_id is not None:
            row = self._fetchone(
                "SELECT * FROM character "
                "WHERE name = %s AND world_id = %s",
                (name, world_id),
            )
        else:
            row = self._fetchone(
                "SELECT * FROM character WHERE name = %s", (name,)
            )
        return Character(**row) if row else None

    def get_locations(self, world_id: int) -> list[Location]:
        rows = self._fetchall(
            "SELECT * FROM location WHERE world_id = %s ORDER BY location_id",
            (world_id,),
        )
        return [Location(**r) for r in rows]

    def get_location(self, location_id: int) -> Location | None:
        row = self._fetchone(
            "SELECT * FROM location WHERE location_id = %s", (location_id,)
        )
        return Location(**row) if row else None

    def get_session(self, session_id: int) -> Session | None:
        row = self._fetchone(
            "SELECT * FROM session WHERE session_id = %s", (session_id,)
        )
        return Session(**row) if row else None

    def get_event(self, event_id: int) -> Event | None:
        row = self._fetchone(
            "SELECT * FROM event WHERE event_id = %s", (event_id,)
        )
        return Event(**row) if row else None

    def get_events_for_session(self, session_id: int) -> list[Event]:
        rows = self._fetchall(
            "SELECT * FROM event WHERE session_id = %s ORDER BY occurred_at",
            (session_id,),
        )
        return [Event(**r) for r in rows]

    def get_event_types(self) -> list[EventType]:
        return [
            EventType(**r)
            for r in self._fetchall("SELECT * FROM event_type ORDER BY label")
        ]

    def get_relationship_types(self) -> list[RelationshipType]:
        return [
            RelationshipType(**r)
            for r in self._fetchall(
                "SELECT * FROM relationship_type ORDER BY label"
            )
        ]

    def get_beliefs_for_agent(
        self, agent_id: int, current_only: bool = True,
    ) -> list[Belief]:
        """All beliefs held by an agent, optionally only current ones."""
        sql = (
            "SELECT * FROM belief WHERE agent_id = %s"
            + (" AND superseded_by IS NULL" if current_only else "")
            + " ORDER BY created_at DESC"
        )
        return [Belief(**r) for r in self._fetchall(sql, (agent_id,))]

    def get_knowledge_events_for_agent(
        self, agent_id: int,
    ) -> list[KnowledgeEvent]:
        """All events an agent knows about."""
        rows = self._fetchall(
            "SELECT * FROM knowledge_event "
            "WHERE agent_id = %s ORDER BY learned_at",
            (agent_id,),
        )
        return [KnowledgeEvent(**r) for r in rows]

    def get_character_current_location(
        self, character_id: int,
    ) -> CharacterLocation | None:
        """Where is a character right now (departed_at IS NULL)?"""
        row = self._fetchone(
            "SELECT * FROM character_location "
            "WHERE character_id = %s AND departed_at IS NULL",
            (character_id,),
        )
        return CharacterLocation(**row) if row else None

    def get_all_conflicts(
        self, resolved: bool | None = None,
    ) -> list[Conflict]:
        """All conflicts, optionally filtered by resolution status."""
        if resolved is None:
            sql = "SELECT * FROM conflict ORDER BY detected_at"
            params: tuple = ()
        elif resolved:
            sql = "SELECT * FROM conflict WHERE resolved_at IS NOT NULL ORDER BY detected_at"
            params = ()
        else:
            sql = "SELECT * FROM conflict WHERE resolved_at IS NULL ORDER BY detected_at"
            params = ()
        return [Conflict(**r) for r in self._fetchall(sql, params)]

    def get_agent_character_mapping(
        self, agent_id: int,
    ) -> AgentCharacter | None:
        """Get the active agent_character row for an agent (if any)."""
        row = self._fetchone(
            "SELECT * FROM agent_character "
            "WHERE agent_id = %s AND unassigned_at IS NULL",
            (agent_id,),
        )
        return AgentCharacter(**row) if row else None

    def get_character_for_agent(self, agent_id: int) -> Character | None:
        """Convenience: return the Character an agent portrays, or None."""
        mapping = self.get_agent_character_mapping(agent_id)
        if mapping is None:
            return None
        return self.get_character(mapping.character_id)
