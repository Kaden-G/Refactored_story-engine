-- ============================================================
-- MAMS — Stage 3c: TRIGGERS
-- A trigger is a function that fires AUTOMATICALLY in response
-- to an INSERT / UPDATE / DELETE on a table. Each trigger has
-- two parts: a trigger FUNCTION (the logic) and the TRIGGER
-- itself (which binds the function to a table + event).
-- ============================================================

-- ------------------------------------------------------------
-- TRIGGER 1: trg_detect_conflict
-- Fires AFTER INSERT on belief.
-- When a new belief is added, it scans for an existing,
-- current belief that:
--   - is about the SAME subject (subject_type + subject_id),
--   - belongs to a DIFFERENT agent,
--   - is high-confidence (>= 0.70), as is the new belief.
-- Each such pair is a candidate contradiction, so a CONFLICT
-- row is inserted automatically.
--
-- Design note: a database cannot judge semantic contradiction
-- the way an LLM can. MAMS therefore flags high-confidence
-- competing beliefs about the same subject as candidate
-- conflicts for review. This is deliberately conservative:
-- the DB surfaces candidates; an agent or human confirms.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_detect_conflict()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_other  RECORD;
BEGIN
    -- only consider reasonably confident new beliefs
    IF NEW.confidence < 0.70 THEN
        RETURN NEW;
    END IF;

    -- look for competing current beliefs about the same subject
    FOR v_other IN
        SELECT b.belief_id
          FROM belief b
         WHERE b.subject_type   = NEW.subject_type
           AND b.subject_id     = NEW.subject_id
           AND b.agent_id      <> NEW.agent_id
           AND b.belief_id     <> NEW.belief_id
           AND b.superseded_by IS NULL
           AND b.confidence     >= 0.70
    LOOP
        -- avoid duplicate conflict rows (either ordering of the pair)
        IF NOT EXISTS (
            SELECT 1 FROM conflict c
             WHERE (c.belief_id_1 = NEW.belief_id AND c.belief_id_2 = v_other.belief_id)
                OR (c.belief_id_1 = v_other.belief_id AND c.belief_id_2 = NEW.belief_id)
        ) THEN
            INSERT INTO conflict (belief_id_1, belief_id_2, conflict_type)
            VALUES (NEW.belief_id, v_other.belief_id, 'belief_belief');

            RAISE NOTICE 'Auto-detected conflict: belief % vs belief %.',
                NEW.belief_id, v_other.belief_id;
        END IF;
    END LOOP;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_detect_conflict
    AFTER INSERT ON belief
    FOR EACH ROW
    EXECUTE FUNCTION fn_detect_conflict();

COMMENT ON FUNCTION fn_detect_conflict() IS
    'Auto-flags high-confidence competing beliefs about the same subject.';

-- ------------------------------------------------------------
-- TRIGGER 2: trg_touch_memory
-- Fires BEFORE UPDATE on memory.
-- Whenever a memory row is updated, automatically refreshes
-- last_accessed_at to the current time. This keeps memory
-- recency accurate without the application having to remember
-- to set it.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_touch_memory()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.last_accessed_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_touch_memory
    BEFORE UPDATE ON memory
    FOR EACH ROW
    EXECUTE FUNCTION fn_touch_memory();

COMMENT ON FUNCTION fn_touch_memory() IS
    'Refreshes memory.last_accessed_at on every update.';

-- ------------------------------------------------------------
-- TRIGGER 3: trg_guard_session_status
-- Fires BEFORE UPDATE on session.
-- Enforces the operational rule that a session is append-only
-- once finished: a session whose status is 'completed' or
-- 'failed' may not be reopened or changed. Also auto-stamps
-- ended_at when a session transitions out of 'active'.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_guard_session_status()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- block any change to an already-finished session
    IF OLD.status IN ('completed','failed') THEN
        RAISE EXCEPTION
            'Session % is % and is immutable; it cannot be modified.',
            OLD.session_id, OLD.status;
    END IF;

    -- when a session leaves 'active', stamp the end time if unset
    IF NEW.status IN ('completed','failed') AND NEW.ended_at IS NULL THEN
        NEW.ended_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_guard_session_status
    BEFORE UPDATE ON session
    FOR EACH ROW
    EXECUTE FUNCTION fn_guard_session_status();

COMMENT ON FUNCTION fn_guard_session_status() IS
    'Makes finished sessions immutable; auto-stamps ended_at.';
