-- ============================================================
-- MAMS — Stage 3a: FUNCTIONS
-- Read-only helpers. A function takes inputs, returns a value
-- or a result set, and does NOT modify data.
-- Written in PL/pgSQL (PostgreSQL's procedural language).
-- ============================================================

-- ------------------------------------------------------------
-- FUNCTION 1: get_conflict_count(agent_id)
-- Returns how many UNRESOLVED conflicts a given agent is part of.
-- An agent is "part of" a conflict if either belief in the
-- conflict belongs to that agent.
-- Returns a single integer.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_conflict_count(p_agent_id INTEGER)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT count(*)
      INTO v_count
      FROM conflict c
      JOIN belief b1 ON c.belief_id_1 = b1.belief_id
      JOIN belief b2 ON c.belief_id_2 = b2.belief_id
     WHERE c.resolved_at IS NULL
       AND (b1.agent_id = p_agent_id OR b2.agent_id = p_agent_id);

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION get_conflict_count(INTEGER) IS
    'Returns the number of unresolved conflicts involving an agent.';

-- ------------------------------------------------------------
-- FUNCTION 2: get_location_occupants(location_id, at_time)
-- Returns every character present at a location at a given time.
-- "Present" means: they arrived on or before at_time, and either
-- have not departed, or departed after at_time.
-- Returns a TABLE (a result set), not a single value.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_location_occupants(
    p_location_id INTEGER,
    p_at_time     TIMESTAMPTZ DEFAULT now()
)
RETURNS TABLE (
    character_id    INTEGER,
    character_name  VARCHAR,
    arrived_at      TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT ch.character_id,
           ch.name,
           cl.arrived_at
      FROM character_location cl
      JOIN character ch ON cl.character_id = ch.character_id
     WHERE cl.location_id = p_location_id
       AND cl.arrived_at <= p_at_time
       AND (cl.departed_at IS NULL OR cl.departed_at > p_at_time)
     ORDER BY cl.arrived_at;
END;
$$;

COMMENT ON FUNCTION get_location_occupants(INTEGER, TIMESTAMPTZ) IS
    'Returns all characters present at a location at a given time.';

-- ------------------------------------------------------------
-- FUNCTION 3: get_agent_belief(agent_id, subject_type, subject_id)
-- Returns an agent's CURRENT belief(s) about a given subject.
-- "Current" means the belief has not been superseded
-- (superseded_by IS NULL). Ordered by confidence, highest first.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_agent_belief(
    p_agent_id      INTEGER,
    p_subject_type  VARCHAR,
    p_subject_id    INTEGER
)
RETURNS TABLE (
    belief_id       INTEGER,
    belief_content  TEXT,
    confidence      NUMERIC,
    created_at      TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT b.belief_id,
           b.belief_content,
           b.confidence,
           b.created_at
      FROM belief b
     WHERE b.agent_id     = p_agent_id
       AND b.subject_type = p_subject_type
       AND b.subject_id   = p_subject_id
       AND b.superseded_by IS NULL
     ORDER BY b.confidence DESC;
END;
$$;

COMMENT ON FUNCTION get_agent_belief(INTEGER, VARCHAR, INTEGER) IS
    'Returns an agent''s current (non-superseded) beliefs about a subject.';
