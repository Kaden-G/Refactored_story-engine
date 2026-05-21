-- ============================================================
-- MAMS — Stage 1, Layer 3: EPISTEMIC LAYER (what agents believe)
-- This is the heart of MAMS — boxes 3 and 4 of the core idea.
-- PostgreSQL 16
-- ============================================================

-- ------------------------------------------------------------
-- MEMORY: a durable extracted fact, scoped to one agent.
-- This is long-term memory — what an agent has learned and
-- retained, surviving across sessions.
-- is_active = FALSE means the memory was superseded but kept
-- for history (MAMS never deletes — audit-first design).
-- ------------------------------------------------------------
CREATE TABLE memory (
    memory_id        INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_id         INTEGER      NOT NULL,
    world_id         INTEGER      NOT NULL,
    content          TEXT         NOT NULL,
    confidence       NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_accessed_at TIMESTAMPTZ,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_memory_agent
        FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_memory_world
        FOREIGN KEY (world_id) REFERENCES world (world_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_memory_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

COMMENT ON TABLE memory IS
    'Durable extracted facts scoped to one agent; the core memory unit.';

-- ------------------------------------------------------------
-- BELIEF: an agent's current understanding of ONE specific fact.
-- This is box 3 of the core idea — "Anna believes the king is dead".
--
-- subject_type + subject_id is a polymorphic reference: a belief
-- can be ABOUT a character, a relationship, an event, etc.
-- We do not put a hard FK on subject_id because it points to
-- different tables depending on subject_type — instead the
-- application and a CHECK constraint keep it disciplined.
--
-- superseded_by points at a newer BELIEF row that replaced this
-- one — a self-referencing FK that builds a history chain.
-- ------------------------------------------------------------
CREATE TABLE belief (
    belief_id       INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_id        INTEGER      NOT NULL,
    subject_type    VARCHAR(30)  NOT NULL,
    subject_id      INTEGER      NOT NULL,
    belief_content  TEXT         NOT NULL,
    confidence      NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    superseded_by   INTEGER,                       -- NULL = current belief

    CONSTRAINT fk_belief_agent
        FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_belief_superseded
        FOREIGN KEY (superseded_by) REFERENCES belief (belief_id)
        ON DELETE RESTRICT,

    -- a belief cannot supersede itself
    CONSTRAINT chk_belief_not_self_supersede
        CHECK (superseded_by IS NULL OR superseded_by <> belief_id),

    CONSTRAINT chk_belief_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0),

    -- subject_type is constrained to known kinds of things
    CONSTRAINT chk_belief_subject_type
        CHECK (subject_type IN
              ('character','relationship','event','location','world_state'))
);

COMMENT ON TABLE belief IS
    'An agent''s current understanding of one fact; may contradict others.';

-- ------------------------------------------------------------
-- KNOWLEDGE_EVENT: records WHEN an agent learned about an event.
-- This is box 2 of the core idea — the provenance of knowledge.
-- learned_via says HOW they found out: they were there (direct),
-- it propagated to them, someone told them, or they inferred it.
-- ------------------------------------------------------------
CREATE TABLE knowledge_event (
    knowledge_event_id  INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_id            INTEGER      NOT NULL,
    event_id            INTEGER      NOT NULL,
    learned_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    learned_via         VARCHAR(20)  NOT NULL DEFAULT 'direct',

    CONSTRAINT fk_knowevent_agent
        FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_knowevent_event
        FOREIGN KEY (event_id) REFERENCES event (event_id)
        ON DELETE RESTRICT,

    -- an agent learns about a given event only once
    CONSTRAINT uq_knowevent UNIQUE (agent_id, event_id),

    CONSTRAINT chk_knowevent_via
        CHECK (learned_via IN ('direct','propagated','told','inferred'))
);

COMMENT ON TABLE knowledge_event IS
    'Records when and how an agent learned about a specific event.';

-- ------------------------------------------------------------
-- CONFLICT: a detected contradiction between two beliefs.
-- This is box 4 of the core idea — the thing a flat file cannot do.
--
-- It links two BELIEF rows. resolved_at NULL means the conflict
-- is still open. resolution_decision_id points at the DECISION
-- that resolved it (an audit link).
-- ------------------------------------------------------------
CREATE TABLE conflict (
    conflict_id             INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    belief_id_1             INTEGER      NOT NULL,
    belief_id_2             INTEGER      NOT NULL,
    conflict_type           VARCHAR(30)  NOT NULL DEFAULT 'belief_belief',
    detected_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    resolved_at             TIMESTAMPTZ,
    resolution_decision_id  INTEGER,

    CONSTRAINT fk_conflict_belief1
        FOREIGN KEY (belief_id_1) REFERENCES belief (belief_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_conflict_belief2
        FOREIGN KEY (belief_id_2) REFERENCES belief (belief_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_conflict_resolution
        FOREIGN KEY (resolution_decision_id) REFERENCES decision (decision_id)
        ON DELETE RESTRICT,

    -- a belief cannot conflict with itself
    CONSTRAINT chk_conflict_distinct
        CHECK (belief_id_1 <> belief_id_2),

    CONSTRAINT chk_conflict_type
        CHECK (conflict_type IN ('belief_belief','belief_worldstate')),

    -- if resolved, there must be a decision explaining it
    CONSTRAINT chk_conflict_resolution
        CHECK ( (resolved_at IS NULL AND resolution_decision_id IS NULL)
             OR (resolved_at IS NOT NULL AND resolution_decision_id IS NOT NULL) )
);

COMMENT ON TABLE conflict IS
    'A detected contradiction between two beliefs; the core MAMS payoff.';

-- ------------------------------------------------------------
-- Indexes on foreign keys.
-- ------------------------------------------------------------
CREATE INDEX idx_memory_agent          ON memory (agent_id);
CREATE INDEX idx_memory_world          ON memory (world_id);
CREATE INDEX idx_belief_agent          ON belief (agent_id);
CREATE INDEX idx_belief_superseded     ON belief (superseded_by);
CREATE INDEX idx_belief_subject        ON belief (subject_type, subject_id);
CREATE INDEX idx_knowevent_agent       ON knowledge_event (agent_id);
CREATE INDEX idx_knowevent_event       ON knowledge_event (event_id);
CREATE INDEX idx_conflict_belief1      ON conflict (belief_id_1);
CREATE INDEX idx_conflict_belief2      ON conflict (belief_id_2);
CREATE INDEX idx_conflict_resolution   ON conflict (resolution_decision_id);
