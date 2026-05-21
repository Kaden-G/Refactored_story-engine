-- ============================================================
-- MAMS — Stage 1, Layer 2: AGENT LAYER (the AI system)
-- PostgreSQL 16
-- ============================================================

-- ------------------------------------------------------------
-- AGENT_TYPE: lookup for agent roles.
-- Director (orchestrator), Specialist (Writer/Lore-keeper/etc.),
-- NPC (portrays a character), Meta (operates above the story).
-- ------------------------------------------------------------
CREATE TABLE agent_type (
    agent_type_id  INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label          VARCHAR(40)  NOT NULL,
    description    TEXT,

    CONSTRAINT uq_agent_type_label UNIQUE (label)
);

COMMENT ON TABLE agent_type IS 'Lookup: Director, Specialist, NPC, Meta.';

-- ------------------------------------------------------------
-- AGENT: an AI agent instance with a role.
-- model_name records which LLM backs it (e.g. claude-opus-4-7).
-- ------------------------------------------------------------
CREATE TABLE agent (
    agent_id        INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    world_id        INTEGER      NOT NULL,
    agent_type_id   INTEGER      NOT NULL,
    name            VARCHAR(120) NOT NULL,
    model_name      VARCHAR(80),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_agent_world
        FOREIGN KEY (world_id) REFERENCES world (world_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_agent_type
        FOREIGN KEY (agent_type_id) REFERENCES agent_type (agent_type_id)
        ON DELETE RESTRICT
);

COMMENT ON TABLE agent IS 'An AI agent instance: Director, Writer, NPC, etc.';

-- ------------------------------------------------------------
-- AGENT_CHARACTER: maps an agent to the character it portrays.
-- Optional relationship — Director/Meta agents portray no one.
-- Temporal: assigned_at / unassigned_at bound the assignment,
-- so control of a character can change hands over time.
-- ------------------------------------------------------------
CREATE TABLE agent_character (
    agent_character_id  INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_id            INTEGER      NOT NULL,
    character_id        INTEGER      NOT NULL,
    assigned_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    unassigned_at       TIMESTAMPTZ,                     -- NULL = still assigned

    CONSTRAINT fk_agentchar_agent
        FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_agentchar_character
        FOREIGN KEY (character_id) REFERENCES character (character_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_agentchar_dates
        CHECK (unassigned_at IS NULL OR unassigned_at > assigned_at)
);

COMMENT ON TABLE agent_character IS
    'Maps an agent to the character it portrays (optional, temporal).';

-- A character can be portrayed by at most ONE agent at a time.
-- This partial unique index enforces it: among rows that are
-- still active (unassigned_at IS NULL), character_id must be unique.
CREATE UNIQUE INDEX uq_agentchar_active_character
    ON agent_character (character_id)
    WHERE unassigned_at IS NULL;

-- ------------------------------------------------------------
-- SESSION: one complete Director loop. The central organizing
-- entity — most functions touch it.
-- status moves active -> completed or active -> failed.
-- ------------------------------------------------------------
CREATE TABLE session (
    session_id          INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    world_id            INTEGER      NOT NULL,
    director_agent_id   INTEGER      NOT NULL,
    started_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ended_at            TIMESTAMPTZ,
    status              VARCHAR(20)  NOT NULL DEFAULT 'active',
    narrative_context   TEXT,

    CONSTRAINT fk_session_world
        FOREIGN KEY (world_id) REFERENCES world (world_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_session_director
        FOREIGN KEY (director_agent_id) REFERENCES agent (agent_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_session_status
        CHECK (status IN ('active','completed','failed')),

    CONSTRAINT chk_session_dates
        CHECK (ended_at IS NULL OR ended_at >= started_at)
);

COMMENT ON TABLE session IS 'One complete Director agent loop; central audit unit.';

-- ------------------------------------------------------------
-- AGENT_SESSION: junction table. Which agents took part in
-- which session, and in what role. Many-to-many resolved.
-- ------------------------------------------------------------
CREATE TABLE agent_session (
    agent_session_id  INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_id          INTEGER      NOT NULL,
    session_id        INTEGER      NOT NULL,
    role              VARCHAR(40)  NOT NULL DEFAULT 'participant',
    joined_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    left_at           TIMESTAMPTZ,

    CONSTRAINT fk_agentsession_agent
        FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_agentsession_session
        FOREIGN KEY (session_id) REFERENCES session (session_id)
        ON DELETE RESTRICT,

    -- the same agent should not be added to the same session twice
    CONSTRAINT uq_agentsession UNIQUE (agent_id, session_id),

    CONSTRAINT chk_agentsession_dates
        CHECK (left_at IS NULL OR left_at >= joined_at)
);

COMMENT ON TABLE agent_session IS
    'Junction: which agents participated in which session.';

-- ------------------------------------------------------------
-- DECISION: a logged action taken by an agent during a session.
-- The audit trail — "who decided what, when, and why".
-- ------------------------------------------------------------
CREATE TABLE decision (
    decision_id     INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_id        INTEGER      NOT NULL,
    session_id      INTEGER      NOT NULL,
    decision_type   VARCHAR(40)  NOT NULL,
    description     TEXT         NOT NULL,
    rationale       TEXT,
    made_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_decision_agent
        FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_decision_session
        FOREIGN KEY (session_id) REFERENCES session (session_id)
        ON DELETE RESTRICT
);

COMMENT ON TABLE decision IS 'Audit trail of agent actions during sessions.';

-- ------------------------------------------------------------
-- Cross-layer link: now that SESSION exists, add the session_id
-- foreign key to EVENT (was flagged as a placeholder in Layer 1).
-- An event may or may not belong to a session, so it is nullable.
-- ------------------------------------------------------------
ALTER TABLE event
    ADD COLUMN session_id INTEGER;

ALTER TABLE event
    ADD CONSTRAINT fk_event_session
    FOREIGN KEY (session_id) REFERENCES session (session_id)
    ON DELETE RESTRICT;

-- ------------------------------------------------------------
-- Indexes on the new foreign keys.
-- ------------------------------------------------------------
CREATE INDEX idx_agent_world         ON agent (world_id);
CREATE INDEX idx_agent_type          ON agent (agent_type_id);
CREATE INDEX idx_agentchar_agent     ON agent_character (agent_id);
CREATE INDEX idx_agentchar_character ON agent_character (character_id);
CREATE INDEX idx_session_world       ON session (world_id);
CREATE INDEX idx_session_director    ON session (director_agent_id);
CREATE INDEX idx_agentsession_agent  ON agent_session (agent_id);
CREATE INDEX idx_agentsession_sess   ON agent_session (session_id);
CREATE INDEX idx_decision_agent      ON decision (agent_id);
CREATE INDEX idx_decision_session    ON decision (session_id);
CREATE INDEX idx_event_session       ON event (session_id);
