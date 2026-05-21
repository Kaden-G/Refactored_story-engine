-- ============================================================
-- MAMS — Multi-Agent Memory Store
-- Stage 1, Layer 1: OBJECTIVE LAYER (ground truth of the world)
-- PostgreSQL 16
-- ============================================================

-- ------------------------------------------------------------
-- WORLD: the top-level container. Every other row belongs to a world.
-- This lets one database hold multiple independent story worlds.
-- ------------------------------------------------------------
CREATE TABLE world (
    world_id      INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          VARCHAR(120)  NOT NULL,
    description   TEXT,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT uq_world_name UNIQUE (name)
);

COMMENT ON TABLE world IS 'Top-level container; a single story world or campaign.';

-- ------------------------------------------------------------
-- LOCATION: places within a world.
-- Self-referencing: parent_location_id points back at LOCATION,
-- which builds the hierarchy World > Region > Building > Room > Point.
-- A root location (e.g. the world map itself) has parent = NULL.
-- grid_x/y/z give precise positioning inside a location.
-- ------------------------------------------------------------
CREATE TABLE location (
    location_id          INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    world_id             INTEGER      NOT NULL,
    parent_location_id   INTEGER,                       -- NULL = top of hierarchy
    name                 VARCHAR(120) NOT NULL,
    location_type        VARCHAR(30)  NOT NULL DEFAULT 'place',
    grid_x               INTEGER,
    grid_y               INTEGER,
    grid_z               INTEGER,

    CONSTRAINT fk_location_world
        FOREIGN KEY (world_id) REFERENCES world (world_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_location_parent
        FOREIGN KEY (parent_location_id) REFERENCES location (location_id)
        ON DELETE RESTRICT,

    -- a location cannot be its own parent
    CONSTRAINT chk_location_not_self_parent
        CHECK (parent_location_id IS NULL OR parent_location_id <> location_id),

    CONSTRAINT chk_location_type
        CHECK (location_type IN ('world','region','building','room','point','place'))
);

COMMENT ON TABLE location IS 'Hierarchical places; self-referencing parent FK plus grid coords.';

-- ------------------------------------------------------------
-- CHARACTER: any narrative entity — person, NPC, weather, crowd,
-- institution. Exists whether or not an AI agent controls it.
-- "character" is a reserved-ish word in some DBs, so we keep the
-- table name as character but always reference it explicitly.
-- ------------------------------------------------------------
CREATE TABLE character (
    character_id    INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    world_id        INTEGER      NOT NULL,
    name            VARCHAR(120) NOT NULL,
    character_type  VARCHAR(30)  NOT NULL DEFAULT 'person',
    description     TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_character_world
        FOREIGN KEY (world_id) REFERENCES world (world_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_character_type
        CHECK (character_type IN
              ('person','npc','weather','crowd','institution','creature','other'))
);

COMMENT ON TABLE character IS 'Narrative entities; exist independently of any AI agent.';

-- ------------------------------------------------------------
-- RELATIONSHIP_TYPE: lookup table for the kinds of relationships
-- two characters can have. A lookup table keeps the values
-- consistent and lets us add new types without schema changes.
-- ------------------------------------------------------------
CREATE TABLE relationship_type (
    relationship_type_id  INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label                 VARCHAR(40)  NOT NULL,
    description           TEXT,

    CONSTRAINT uq_relationship_type_label UNIQUE (label)
);

COMMENT ON TABLE relationship_type IS 'Lookup: trusts, fears, allied, hostile, etc.';

-- ------------------------------------------------------------
-- EVENT_TYPE: lookup table for categories of events.
-- ------------------------------------------------------------
CREATE TABLE event_type (
    event_type_id  INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label          VARCHAR(40)  NOT NULL,
    description    TEXT,

    CONSTRAINT uq_event_type_label UNIQUE (label)
);

COMMENT ON TABLE event_type IS 'Lookup: dialogue, combat, discovery, movement, etc.';

-- ------------------------------------------------------------
-- CHARACTER_RELATIONSHIP: a directed relationship between two
-- characters, with temporal validity (valid_from / valid_until).
-- Temporal because relationships change — Anna may trust Sam
-- early in the story and distrust him later.
-- intensity (0.0-1.0) captures how strong the relationship is.
-- ------------------------------------------------------------
CREATE TABLE character_relationship (
    relationship_id        INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    character_id_from      INTEGER      NOT NULL,
    character_id_to        INTEGER      NOT NULL,
    relationship_type_id   INTEGER      NOT NULL,
    intensity              NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    valid_from             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    valid_until            TIMESTAMPTZ,                  -- NULL = still in effect

    CONSTRAINT fk_charrel_from
        FOREIGN KEY (character_id_from) REFERENCES character (character_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_charrel_to
        FOREIGN KEY (character_id_to) REFERENCES character (character_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_charrel_type
        FOREIGN KEY (relationship_type_id)
        REFERENCES relationship_type (relationship_type_id)
        ON DELETE RESTRICT,

    -- a character cannot have a relationship with itself
    CONSTRAINT chk_charrel_not_self
        CHECK (character_id_from <> character_id_to),

    -- intensity must be a probability-style value
    CONSTRAINT chk_charrel_intensity
        CHECK (intensity >= 0.0 AND intensity <= 1.0),

    -- if an end date exists, it must be after the start date
    CONSTRAINT chk_charrel_dates
        CHECK (valid_until IS NULL OR valid_until > valid_from)
);

COMMENT ON TABLE character_relationship IS
    'Directed, temporal relationships between characters (objective layer).';

-- ------------------------------------------------------------
-- CHARACTER_LOCATION: where a character was, and when.
-- arrived_at / departed_at bound the stay. departed_at NULL
-- means the character is currently there.
-- grid_x/y record precise position for proximity queries.
-- ------------------------------------------------------------
CREATE TABLE character_location (
    char_location_id   INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    character_id       INTEGER      NOT NULL,
    location_id        INTEGER      NOT NULL,
    grid_x             INTEGER,
    grid_y             INTEGER,
    arrived_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    departed_at        TIMESTAMPTZ,                      -- NULL = still present

    CONSTRAINT fk_charloc_character
        FOREIGN KEY (character_id) REFERENCES character (character_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_charloc_location
        FOREIGN KEY (location_id) REFERENCES location (location_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_charloc_dates
        CHECK (departed_at IS NULL OR departed_at > arrived_at)
);

COMMENT ON TABLE character_location IS
    'Time-bounded record of a character at a location, with grid position.';

-- ------------------------------------------------------------
-- EVENT: something that happened, anchored to a time and place.
-- session_id FK is added later, after the SESSION table exists
-- (Agent Layer). We note it here as a placeholder comment.
-- ------------------------------------------------------------
CREATE TABLE event (
    event_id        INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    world_id        INTEGER      NOT NULL,
    location_id     INTEGER,                             -- where it happened
    event_type_id   INTEGER      NOT NULL,
    description     TEXT         NOT NULL,
    occurred_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    -- session_id INTEGER  -- FK added in Agent Layer script

    CONSTRAINT fk_event_world
        FOREIGN KEY (world_id) REFERENCES world (world_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_event_location
        FOREIGN KEY (location_id) REFERENCES location (location_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_event_type
        FOREIGN KEY (event_type_id) REFERENCES event_type (event_type_id)
        ON DELETE RESTRICT
);

COMMENT ON TABLE event IS 'Something that happened, anchored in time and location.';

-- ------------------------------------------------------------
-- Indexes on foreign keys.
-- PostgreSQL does NOT auto-index FK columns. Indexing them speeds
-- up joins and the proximity/lookup queries MAMS will run a lot.
-- ------------------------------------------------------------
CREATE INDEX idx_location_world          ON location (world_id);
CREATE INDEX idx_location_parent         ON location (parent_location_id);
CREATE INDEX idx_character_world         ON character (world_id);
CREATE INDEX idx_charrel_from            ON character_relationship (character_id_from);
CREATE INDEX idx_charrel_to              ON character_relationship (character_id_to);
CREATE INDEX idx_charloc_character       ON character_location (character_id);
CREATE INDEX idx_charloc_location        ON character_location (location_id);
CREATE INDEX idx_event_world             ON event (world_id);
CREATE INDEX idx_event_location          ON event (location_id);
