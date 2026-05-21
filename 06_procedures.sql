-- ============================================================
-- MAMS — Stage 3b: STORED PROCEDURES
-- Procedures perform multi-step operations that MODIFY data.
-- Unlike functions, they do not return a value; they are
-- invoked with CALL and can commit transactional work.
-- ============================================================

-- ------------------------------------------------------------
-- PROCEDURE 1: start_session(world_id, director_agent_id,
--                            narrative_context)
-- Opens a new Director session and enrolls every active agent
-- in that world into agent_session. The new session_id is
-- returned via an INOUT parameter.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE start_session(
    p_world_id          INTEGER,
    p_director_agent_id INTEGER,
    p_narrative_context TEXT,
    INOUT p_session_id  INTEGER DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- create the session row
    INSERT INTO session (world_id, director_agent_id, status, narrative_context)
    VALUES (p_world_id, p_director_agent_id, 'active', p_narrative_context)
    RETURNING session_id INTO p_session_id;

    -- enroll every active agent in this world
    INSERT INTO agent_session (agent_id, session_id, role)
    SELECT a.agent_id,
           p_session_id,
           CASE WHEN a.agent_id = p_director_agent_id
                THEN 'director' ELSE 'participant' END
      FROM agent a
     WHERE a.world_id = p_world_id
       AND a.is_active = TRUE;

    RAISE NOTICE 'Session % started with % agents.',
        p_session_id,
        (SELECT count(*) FROM agent_session WHERE session_id = p_session_id);
END;
$$;

COMMENT ON PROCEDURE start_session(INTEGER, INTEGER, TEXT, INTEGER) IS
    'Opens a session and enrolls all active agents in the world.';

-- ------------------------------------------------------------
-- PROCEDURE 2: propagate_event(event_id)
-- Distributes knowledge of an event to every agent whose
-- character was present at the event's location. Inserts a
-- knowledge_event row for each (skipping any that already
-- exist), then logs a DECISION recording what was propagated.
-- This is the "box 2" mechanic from the core idea.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE propagate_event(p_event_id INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
    v_location_id   INTEGER;
    v_occurred_at   TIMESTAMPTZ;
    v_session_id    INTEGER;
    v_director_id   INTEGER;
    v_count         INTEGER := 0;
BEGIN
    -- look up the event's location, time, and session
    SELECT location_id, occurred_at, session_id
      INTO v_location_id, v_occurred_at, v_session_id
      FROM event
     WHERE event_id = p_event_id;

    IF v_location_id IS NULL THEN
        RAISE EXCEPTION 'Event % has no location; cannot propagate.', p_event_id;
    END IF;

    -- find agents whose character was at that location at that time,
    -- and insert a knowledge_event for each one that does not
    -- already know about this event.
    INSERT INTO knowledge_event (agent_id, event_id, learned_via)
    SELECT DISTINCT ac.agent_id, p_event_id, 'propagated'
      FROM character_location cl
      JOIN agent_character ac
        ON ac.character_id = cl.character_id
       AND ac.unassigned_at IS NULL
     WHERE cl.location_id = v_location_id
       AND cl.arrived_at <= v_occurred_at
       AND (cl.departed_at IS NULL OR cl.departed_at > v_occurred_at)
       AND NOT EXISTS (
            SELECT 1 FROM knowledge_event ke
             WHERE ke.agent_id = ac.agent_id
               AND ke.event_id = p_event_id
       );

    GET DIAGNOSTICS v_count = ROW_COUNT;

    -- log a decision in the audit trail (use the session's director)
    IF v_session_id IS NOT NULL THEN
        SELECT director_agent_id INTO v_director_id
          FROM session WHERE session_id = v_session_id;

        INSERT INTO decision
            (agent_id, session_id, decision_type, description, rationale)
        VALUES (v_director_id, v_session_id, 'knowledge_propagation',
                format('Propagated event %s to %s newly-informed agent(s).',
                       p_event_id, v_count),
                'Agents present at the event location were granted '
                || 'knowledge of the event.');
    END IF;

    RAISE NOTICE 'Event % propagated to % new agent(s).', p_event_id, v_count;
END;
$$;

COMMENT ON PROCEDURE propagate_event(INTEGER) IS
    'Distributes event knowledge to agents present at the event location.';

-- ------------------------------------------------------------
-- PROCEDURE 3: resolve_conflict(conflict_id, winning_belief_id,
--                               resolving_agent_id, rationale)
-- Resolves a conflict by: marking the losing belief superseded
-- by the winning belief, logging a DECISION that records the
-- rationale, and stamping the conflict resolved + linking it
-- to that decision.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE resolve_conflict(
    p_conflict_id        INTEGER,
    p_winning_belief_id  INTEGER,
    p_resolving_agent_id INTEGER,
    p_rationale          TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_belief_1     INTEGER;
    v_belief_2     INTEGER;
    v_losing       INTEGER;
    v_session_id   INTEGER;
    v_decision_id  INTEGER;
BEGIN
    -- fetch the two beliefs in this conflict
    SELECT belief_id_1, belief_id_2
      INTO v_belief_1, v_belief_2
      FROM conflict
     WHERE conflict_id = p_conflict_id;

    IF v_belief_1 IS NULL THEN
        RAISE EXCEPTION 'Conflict % not found.', p_conflict_id;
    END IF;

    -- the winning belief must be one of the two in the conflict
    IF p_winning_belief_id NOT IN (v_belief_1, v_belief_2) THEN
        RAISE EXCEPTION 'Belief % is not part of conflict %.',
            p_winning_belief_id, p_conflict_id;
    END IF;

    -- identify the losing belief
    v_losing := CASE WHEN p_winning_belief_id = v_belief_1
                     THEN v_belief_2 ELSE v_belief_1 END;

    -- pick a session for the audit decision: the resolving agent's
    -- most recent session.
    SELECT session_id INTO v_session_id
      FROM agent_session
     WHERE agent_id = p_resolving_agent_id
     ORDER BY joined_at DESC
     LIMIT 1;

    -- log the resolution decision
    INSERT INTO decision
        (agent_id, session_id, decision_type, description, rationale)
    VALUES (p_resolving_agent_id, v_session_id, 'conflict_resolution',
            format('Resolved conflict %s in favor of belief %s.',
                   p_conflict_id, p_winning_belief_id),
            p_rationale)
    RETURNING decision_id INTO v_decision_id;

    -- mark the losing belief superseded by the winning belief
    UPDATE belief
       SET superseded_by = p_winning_belief_id
     WHERE belief_id = v_losing;

    -- stamp the conflict resolved and link the decision
    UPDATE conflict
       SET resolved_at            = now(),
           resolution_decision_id = v_decision_id
     WHERE conflict_id = p_conflict_id;

    RAISE NOTICE 'Conflict % resolved; belief % superseded by belief %.',
        p_conflict_id, v_losing, p_winning_belief_id;
END;
$$;

COMMENT ON PROCEDURE resolve_conflict(INTEGER, INTEGER, INTEGER, TEXT) IS
    'Resolves a conflict, supersedes the losing belief, logs the decision.';
