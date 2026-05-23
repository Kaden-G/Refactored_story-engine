-- ============================================================
-- MAMS — Stage 2: SEED DATA
-- World: Greywatch (an Elder-Scrolls-flavored guardianship saga)
--
-- A curated slice: 7 characters, 5 locations, the agents that
-- portray them, one session, key events, and the centerpiece —
-- the split-map conflict: different agents hold contradictory
-- beliefs about where Door Three lies.
--
-- Run AFTER the three schema scripts. Uses a DO block so we
-- never hard-code IDENTITY-generated primary keys.
-- ============================================================

DO $$
DECLARE
    v_world         INTEGER;
    -- locations
    loc_falkreath   INTEGER;
    loc_greywatch   INTEGER;
    loc_throat      INTEGER;
    loc_markarth    INTEGER;
    loc_riften      INTEGER;
    -- relationship types
    rt_trusts       INTEGER;
    rt_distrusts    INTEGER;
    rt_allied       INTEGER;
    rt_mentor       INTEGER;
    rt_romantic     INTEGER;
    -- event types
    et_dialogue     INTEGER;
    et_combat       INTEGER;
    et_discovery    INTEGER;
    et_environment  INTEGER;
    et_decision     INTEGER;
    -- agent types
    at_director     INTEGER;
    at_specialist   INTEGER;
    at_npc          INTEGER;
    at_meta         INTEGER;
    -- characters
    c_varen         INTEGER;
    c_lydia         INTEGER;
    c_ralof         INTEGER;
    c_erandur       INTEGER;
    c_kharjo        INTEGER;
    c_sylara        INTEGER;
    c_ondolemar     INTEGER;
    -- agents
    a_director      INTEGER;
    a_lorekeeper    INTEGER;
    a_varen         INTEGER;
    a_lydia         INTEGER;
    a_ondolemar     INTEGER;
    -- session
    s_one           INTEGER;
    -- events
    e_helgen        INTEGER;
    e_doorone       INTEGER;
    e_mapsplit      INTEGER;
    -- beliefs
    b_varen_map     INTEGER;
    b_ondo_map      INTEGER;
    -- decisions
    d_propagate     INTEGER;
BEGIN

  -- ==========================================================
  -- WORLD
  -- ==========================================================
  INSERT INTO world (name, description)
  VALUES ('Greywatch',
          'A guardianship saga: a former assassin founds a lodge to '
          || 'seal three ancient doors before a secret society can '
          || 'reach them. Built on least-privilege information policy.')
  RETURNING world_id INTO v_world;

  -- ==========================================================
  -- LOCATIONS  (Falkreath Hold contains Greywatch lodge)
  -- ==========================================================
  INSERT INTO location (world_id, parent_location_id, name, location_type, grid_x, grid_y)
  VALUES (v_world, NULL, 'Falkreath Hold', 'region', 20, 40)
  RETURNING location_id INTO loc_falkreath;

  INSERT INTO location (world_id, parent_location_id, name, location_type, grid_x, grid_y)
  VALUES (v_world, loc_falkreath, 'Greywatch Lodge', 'building', 22, 41)
  RETURNING location_id INTO loc_greywatch;

  INSERT INTO location (world_id, parent_location_id, name, location_type, grid_x, grid_y)
  VALUES (v_world, NULL, 'The Throat of the World', 'point', 55, 70)
  RETURNING location_id INTO loc_throat;

  INSERT INTO location (world_id, parent_location_id, name, location_type, grid_x, grid_y)
  VALUES (v_world, NULL, 'Markarth', 'building', 8, 55)
  RETURNING location_id INTO loc_markarth;

  INSERT INTO location (world_id, parent_location_id, name, location_type, grid_x, grid_y)
  VALUES (v_world, NULL, 'Riften', 'building', 70, 30)
  RETURNING location_id INTO loc_riften;

  -- ==========================================================
  -- LOOKUP: relationship types
  -- ==========================================================
  INSERT INTO relationship_type (label, description)
  VALUES ('trusts', 'One character trusts another')
  RETURNING relationship_type_id INTO rt_trusts;

  INSERT INTO relationship_type (label, description)
  VALUES ('distrusts', 'One character distrusts another')
  RETURNING relationship_type_id INTO rt_distrusts;

  INSERT INTO relationship_type (label, description)
  VALUES ('allied', 'Two characters are formally allied')
  RETURNING relationship_type_id INTO rt_allied;

  INSERT INTO relationship_type (label, description)
  VALUES ('mentor', 'One character mentored or trained another')
  RETURNING relationship_type_id INTO rt_mentor;

  INSERT INTO relationship_type (label, description)
  VALUES ('romantic', 'A developing romantic relationship')
  RETURNING relationship_type_id INTO rt_romantic;

  -- ==========================================================
  -- LOOKUP: event types
  -- ==========================================================
  INSERT INTO event_type (label, description)
  VALUES ('dialogue', 'Characters speaking') RETURNING event_type_id INTO et_dialogue;
  INSERT INTO event_type (label, description)
  VALUES ('combat', 'A fight or violent act') RETURNING event_type_id INTO et_combat;
  INSERT INTO event_type (label, description)
  VALUES ('discovery', 'Something discovered or revealed') RETURNING event_type_id INTO et_discovery;
  INSERT INTO event_type (label, description)
  VALUES ('environmental', 'A change in the world environment') RETURNING event_type_id INTO et_environment;
  INSERT INTO event_type (label, description)
  VALUES ('decision', 'A deliberate choice with consequences') RETURNING event_type_id INTO et_decision;

  -- ==========================================================
  -- LOOKUP: agent types
  -- ==========================================================
  INSERT INTO agent_type (label, description)
  VALUES ('Director', 'Orchestrates the multi-agent session')
  RETURNING agent_type_id INTO at_director;
  INSERT INTO agent_type (label, description)
  VALUES ('Specialist', 'A specialist agent (Lore-keeper, Writer, etc.)')
  RETURNING agent_type_id INTO at_specialist;
  INSERT INTO agent_type (label, description)
  VALUES ('NPC', 'An agent that portrays a single character')
  RETURNING agent_type_id INTO at_npc;
  INSERT INTO agent_type (label, description)
  VALUES ('Meta', 'An agent operating above the story')
  RETURNING agent_type_id INTO at_meta;

  -- ==========================================================
  -- CHARACTERS  (7-character curated slice)
  -- ==========================================================
  INSERT INTO character (world_id, name, character_type, description)
  VALUES (v_world, 'Varen Indoril', 'person',
          'Dunmer Guardian of Greywatch; former Dark Brotherhood; '
          || 'calm, decisive, Keeper of the Coin.')
  RETURNING character_id INTO c_varen;

  INSERT INTO character (world_id, name, character_type, description)
  VALUES (v_world, 'Lydia', 'person',
          'Nord Warden of Greywatch; former Thalmor, trained under '
          || 'Ondolemar; counter-intelligence and threat assessment.')
  RETURNING character_id INTO c_lydia;

  INSERT INTO character (world_id, name, character_type, description)
  VALUES (v_world, 'Ralof', 'person',
          'Nord Sentinel of Greywatch; former Stormcloak; field '
          || 'operations and physical security.')
  RETURNING character_id INTO c_ralof;

  INSERT INTO character (world_id, name, character_type, description)
  VALUES (v_world, 'Erandur', 'person',
          'Nord Lorekeeper of Greywatch; former monk of High '
          || 'Hrothgar; keeper of old knowledge and correspondence.')
  RETURNING character_id INTO c_erandur;

  INSERT INTO character (world_id, name, character_type, description)
  VALUES (v_world, 'Kharjo', 'person',
          'Khajiit Outrider of Greywatch; logistics, contacts, '
          || 'caravan network; always prepared.')
  RETURNING character_id INTO c_kharjo;

  INSERT INTO character (world_id, name, character_type, description)
  VALUES (v_world, 'Sylara', 'person',
          'Associate of Greywatch; Varen''s former Dark Brotherhood '
          || 'handler; flexible field presence.')
  RETURNING character_id INTO c_sylara;

  INSERT INTO character (world_id, name, character_type, description)
  VALUES (v_world, 'Ondolemar', 'person',
          'Altmer Thalmor Justiciar; probationary petitioner to '
          || 'Greywatch; deliberately given partial information.')
  RETURNING character_id INTO c_ondolemar;

  -- ==========================================================
  -- AGENTS  (5 agents: Director, Lorekeeper specialist, 3 NPCs)
  -- ==========================================================
  INSERT INTO agent (world_id, agent_type_id, name, model_name)
  VALUES (v_world, at_director, 'Director Agent', 'claude-opus-4-7')
  RETURNING agent_id INTO a_director;

  INSERT INTO agent (world_id, agent_type_id, name, model_name)
  VALUES (v_world, at_specialist, 'Lorekeeper Agent', 'claude-opus-4-7')
  RETURNING agent_id INTO a_lorekeeper;

  INSERT INTO agent (world_id, agent_type_id, name, model_name)
  VALUES (v_world, at_npc, 'Varen NPC Agent', 'claude-opus-4-7')
  RETURNING agent_id INTO a_varen;

  INSERT INTO agent (world_id, agent_type_id, name, model_name)
  VALUES (v_world, at_npc, 'Lydia NPC Agent', 'claude-opus-4-7')
  RETURNING agent_id INTO a_lydia;

  INSERT INTO agent (world_id, agent_type_id, name, model_name)
  VALUES (v_world, at_npc, 'Ondolemar NPC Agent', 'claude-opus-4-7')
  RETURNING agent_id INTO a_ondolemar;

  -- ==========================================================
  -- AGENT_CHARACTER  (which agent portrays which character)
  -- Director and Lorekeeper portray no one (meta/specialist).
  -- ==========================================================
  INSERT INTO agent_character (agent_id, character_id)
  VALUES (a_varen, c_varen);
  INSERT INTO agent_character (agent_id, character_id)
  VALUES (a_lydia, c_lydia);
  INSERT INTO agent_character (agent_id, character_id)
  VALUES (a_ondolemar, c_ondolemar);

  -- ==========================================================
  -- SESSION  (one Director loop)
  -- ==========================================================
  INSERT INTO session (world_id, director_agent_id, status, narrative_context)
  VALUES (v_world, a_director, 'active',
          'Establish the Door Three search: place characters, '
          || 'log the map split, propagate knowledge, surface the '
          || 'resulting conflict between Varen and Ondolemar.')
  RETURNING session_id INTO s_one;

  -- AGENT_SESSION: all five agents participate in this session
  INSERT INTO agent_session (agent_id, session_id, role) VALUES
    (a_director,   s_one, 'director'),
    (a_lorekeeper, s_one, 'specialist'),
    (a_varen,      s_one, 'participant'),
    (a_lydia,      s_one, 'participant'),
    (a_ondolemar,  s_one, 'participant');

  -- ==========================================================
  -- CHARACTER_LOCATION  (where characters are right now)
  -- Greywatch members at the lodge; Ondolemar in Markarth.
  -- ==========================================================
  INSERT INTO character_location (character_id, location_id, grid_x, grid_y) VALUES
    (c_varen,     loc_greywatch, 22, 41),
    (c_lydia,     loc_greywatch, 22, 41),
    (c_ralof,     loc_greywatch, 22, 41),
    (c_erandur,   loc_greywatch, 22, 41),
    (c_kharjo,    loc_riften,    70, 30),   -- Kharjo working contacts in Riften
    (c_sylara,    loc_markarth,  8,  55),   -- Sylara in the field at Markarth
    (c_ondolemar, loc_markarth,  8,  55);   -- Ondolemar in his own territory

  -- ==========================================================
  -- CHARACTER_RELATIONSHIPS
  -- ==========================================================
  INSERT INTO character_relationship
    (character_id_from, character_id_to, relationship_type_id, intensity) VALUES
    (c_varen,     c_sylara,    rt_romantic,  0.75),
    (c_varen,     c_kharjo,    rt_trusts,    0.85),
    (c_varen,     c_lydia,     rt_trusts,    0.80),
    (c_varen,     c_ralof,     rt_trusts,    0.85),
    (c_varen,     c_erandur,   rt_trusts,    0.80),
    (c_varen,     c_ondolemar, rt_distrusts, 0.60),
    (c_ondolemar, c_lydia,     rt_mentor,    0.70),
    (c_lydia,     c_ralof,     rt_allied,    0.55);

  -- ==========================================================
  -- EVENTS  (anchored in time + location + session)
  -- ==========================================================
  INSERT INTO event (world_id, location_id, event_type_id, description, session_id)
  VALUES (v_world, loc_falkreath, et_combat,
          'The dragon attack at Helgen; Varen survives his execution '
          || 'and recovers the courier''s satchel.', s_one)
  RETURNING event_id INTO e_helgen;

  INSERT INTO event (world_id, location_id, event_type_id, description, session_id)
  VALUES (v_world, loc_throat, et_decision,
          'Door One is sealed at the Throat of the World using the Coin.',
          s_one)
  RETURNING event_id INTO e_doorone;

  -- THE CENTERPIECE EVENT: the map split.
  INSERT INTO event (world_id, location_id, event_type_id, description, session_id)
  VALUES (v_world, loc_markarth, et_discovery,
          'Faendal''s map is split: two of three reference points are '
          || 'delivered to the Unwritten, the third is kept hidden. '
          || 'The true location of Door Three is now contested.', s_one)
  RETURNING event_id INTO e_mapsplit;

  -- ==========================================================
  -- KNOWLEDGE_EVENT  (who learned about the map split, and how)
  -- Varen was at Greywatch when it happened, so Sylara TOLD him.
  -- Ondolemar was in Markarth too, but only caught partial intel.
  -- Lydia has NOT learned it yet — she is at Greywatch.
  -- ==========================================================
  INSERT INTO knowledge_event (agent_id, event_id, learned_via) VALUES
    (a_varen,     e_mapsplit, 'told'),
    (a_ondolemar, e_mapsplit, 'inferred'),
    (a_varen,     e_helgen,   'direct'),
    (a_varen,     e_doorone,  'direct'),
    (a_lydia,     e_doorone,  'direct');
  -- (note: a_lydia has no knowledge_event for e_mapsplit — by design)

  -- ==========================================================
  -- BELIEFS  (box 3 of the core idea)
  -- Varen and Ondolemar believe DIFFERENT things about Door Three.
  -- subject_type 'event' + subject_id = the map-split event.
  -- ==========================================================
  INSERT INTO belief
    (agent_id, subject_type, subject_id, belief_content, confidence)
  VALUES (a_varen, 'event', e_mapsplit,
          'Door Three lies at the hidden third reference point. The '
          || 'Unwritten hold only two points and cannot triangulate '
          || 'the true center.', 0.90)
  RETURNING belief_id INTO b_varen_map;

  INSERT INTO belief
    (agent_id, subject_type, subject_id, belief_content, confidence)
  VALUES (a_ondolemar, 'event', e_mapsplit,
          'Door Three can be triangulated from the two reference '
          || 'points the Unwritten already hold; the third point is '
          || 'redundant.', 0.65)
  RETURNING belief_id INTO b_ondo_map;

  -- ==========================================================
  -- CONFLICT  (box 4 of the core idea)
  -- Varen's belief and Ondolemar's belief contradict each other.
  -- Left UNRESOLVED on purpose, so the queries have something
  -- real to surface. resolved_at + decision stay NULL.
  -- ==========================================================
  INSERT INTO conflict
    (belief_id_1, belief_id_2, conflict_type)
  VALUES (b_varen_map, b_ondo_map, 'belief_belief');

  -- ==========================================================
  -- MEMORY  (durable extracted facts per agent)
  -- ==========================================================
  INSERT INTO memory (agent_id, world_id, content, confidence) VALUES
    (a_varen, v_world,
     'The Coin returns to its keeper and grows reverent near '
     || 'Alessia''s name.', 0.95),
    (a_varen, v_world,
     'Ondolemar is probationary and must not receive full door '
     || 'intelligence until trust is established.', 0.85),
    (a_lydia, v_world,
     'Ondolemar trained me under the Thalmor; his methods are '
     || 'precise but his loyalties are unproven.', 0.80),
    (a_lorekeeper, v_world,
     'Faendal deliberately split his map; the third reference '
     || 'point is the only one that fixes Door Three''s true center.',
     0.90),
    (a_ondolemar, v_world,
     'Greywatch has granted me probationary access only. I have '
     || 'not been shown the full map.', 0.90);

  -- ==========================================================
  -- DECISION  (audit trail entry)
  -- ==========================================================
  INSERT INTO decision
    (agent_id, session_id, decision_type, description, rationale)
  VALUES (a_director, s_one, 'knowledge_propagation',
          'Propagated the map-split event to agents present at '
          || 'Markarth (Varen via Sylara, Ondolemar via inference).',
          'Least-privilege policy: Lydia remained at Greywatch and '
          || 'was not in range to learn of the split.')
  RETURNING decision_id INTO d_propagate;

  RAISE NOTICE 'Greywatch seed data loaded successfully.';

END $$;
