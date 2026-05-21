-- ============================================================
-- MAMS — Stage 4: QUERIES
-- The 10 queries that form the functional interface of MAMS.
-- Each is written to run against the freshly seeded Greywatch
-- world (the state produced by 00_run_all.sql).
--
-- Run individually, or all at once to see every result:
--   psql -d mams -f 08_queries.sql
-- ============================================================

\echo '========================================================'
\echo 'QUERY 1: All memories for a given agent, newest first'
\echo '  (the Varen NPC Agent)'
\echo '========================================================'
SELECT m.memory_id,
       m.content,
       m.confidence,
       m.created_at
  FROM memory m
  JOIN agent a ON m.agent_id = a.agent_id
 WHERE a.name = 'Varen NPC Agent'
   AND m.is_active = TRUE
 ORDER BY m.created_at DESC;


\echo ''
\echo '========================================================'
\echo 'QUERY 2: All unresolved conflicts, with the agents and'
\echo '  beliefs involved'
\echo '========================================================'
SELECT c.conflict_id,
       a1.name            AS agent_1,
       b1.belief_content  AS belief_1,
       a2.name            AS agent_2,
       b2.belief_content  AS belief_2,
       c.detected_at
  FROM conflict c
  JOIN belief b1 ON c.belief_id_1 = b1.belief_id
  JOIN belief b2 ON c.belief_id_2 = b2.belief_id
  JOIN agent  a1 ON b1.agent_id   = a1.agent_id
  JOIN agent  a2 ON b2.agent_id   = a2.agent_id
 WHERE c.resolved_at IS NULL
 ORDER BY c.conflict_id;


\echo ''
\echo '========================================================'
\echo 'QUERY 3: Characters present at a location during an event'
\echo '  (everyone at Markarth when the map was split)'
\echo '========================================================'
SELECT ch.name        AS character_name,
       ch.character_type,
       cl.arrived_at
  FROM event e
  JOIN character_location cl
    ON cl.location_id = e.location_id
   AND cl.arrived_at <= e.occurred_at
   AND (cl.departed_at IS NULL OR cl.departed_at > e.occurred_at)
  JOIN character ch ON cl.character_id = ch.character_id
 WHERE e.description LIKE 'Faendal%map is split%'
 ORDER BY ch.name;


\echo ''
\echo '========================================================'
\echo 'QUERY 4: Agent belief vs. world divergence report'
\echo '  (every agent belief about the map-split event,'
\echo '   side by side, so divergence is visible)'
\echo '========================================================'
SELECT a.name            AS agent,
       b.belief_content,
       b.confidence,
       CASE WHEN b.superseded_by IS NULL
            THEN 'current' ELSE 'superseded' END AS belief_state
  FROM belief b
  JOIN agent a ON b.agent_id = a.agent_id
 WHERE b.subject_type = 'event'
   AND b.subject_id   = (SELECT event_id FROM event
                          WHERE description LIKE 'Faendal%map is split%')
 ORDER BY b.confidence DESC;


\echo ''
\echo '========================================================'
\echo 'QUERY 5: Full decision audit trail for a session'
\echo '========================================================'
SELECT d.made_at,
       a.name           AS decided_by,
       d.decision_type,
       d.description,
       d.rationale
  FROM decision d
  JOIN agent   a ON d.agent_id   = a.agent_id
  JOIN session s ON d.session_id = s.session_id
 WHERE s.session_id = 1
 ORDER BY d.made_at;


\echo ''
\echo '========================================================'
\echo 'QUERY 6: Relationship history between two characters'
\echo '  (Varen and Ondolemar, over time)'
\echo '========================================================'
SELECT cf.name            AS from_character,
       ct.name            AS to_character,
       rt.label           AS relationship,
       cr.intensity,
       cr.valid_from,
       COALESCE(cr.valid_until::text, 'still in effect') AS valid_until
  FROM character_relationship cr
  JOIN character cf        ON cr.character_id_from   = cf.character_id
  JOIN character ct        ON cr.character_id_to     = ct.character_id
  JOIN relationship_type rt ON cr.relationship_type_id = rt.relationship_type_id
 WHERE (cf.name = 'Varen Indoril' AND ct.name = 'Ondolemar')
    OR (cf.name = 'Ondolemar'     AND ct.name = 'Varen Indoril')
 ORDER BY cr.valid_from;


\echo ''
\echo '========================================================'
\echo 'QUERY 7: Which agents know about a given event, and which'
\echo '  do NOT (the map-split event)'
\echo '========================================================'
SELECT a.name AS agent,
       CASE WHEN ke.knowledge_event_id IS NULL
            THEN 'does NOT know'
            ELSE 'knows (via ' || ke.learned_via || ')'
       END AS knowledge_status
  FROM agent a
  LEFT JOIN knowledge_event ke
    ON ke.agent_id = a.agent_id
   AND ke.event_id = (SELECT event_id FROM event
                       WHERE description LIKE 'Faendal%map is split%')
 WHERE a.agent_type_id = (SELECT agent_type_id FROM agent_type WHERE label='NPC')
 ORDER BY knowledge_status, a.name;


\echo ''
\echo '========================================================'
\echo 'QUERY 8: Location hierarchy of the world'
\echo '  (recursive query — walks the self-referencing tree)'
\echo '========================================================'
WITH RECURSIVE loc_tree AS (
    -- anchor: top-level locations (no parent)
    SELECT location_id, name, parent_location_id, 1 AS depth,
           name::text AS path
      FROM location
     WHERE parent_location_id IS NULL
    UNION ALL
    -- recursive step: children of locations already in the tree
    SELECT l.location_id, l.name, l.parent_location_id, lt.depth + 1,
           lt.path || ' > ' || l.name
      FROM location l
      JOIN loc_tree lt ON l.parent_location_id = lt.location_id
)
SELECT depth,
       repeat('    ', depth - 1) || name AS indented_location,
       path
  FROM loc_tree
 ORDER BY path;


\echo ''
\echo '========================================================'
\echo 'QUERY 9: Conflict count per agent'
\echo '  (uses the get_conflict_count function from Stage 3)'
\echo '========================================================'
SELECT a.name AS agent,
       get_conflict_count(a.agent_id) AS unresolved_conflicts
  FROM agent a
 WHERE a.agent_type_id = (SELECT agent_type_id FROM agent_type WHERE label='NPC')
 ORDER BY unresolved_conflicts DESC, a.name;


\echo ''
\echo '========================================================'
\echo 'QUERY 10: Session summary — decisions, events, conflicts'
\echo '  generated during the session'
\echo '========================================================'
SELECT s.session_id,
       s.status,
       s.narrative_context,
       (SELECT count(*) FROM event    e WHERE e.session_id = s.session_id) AS events,
       (SELECT count(*) FROM decision d WHERE d.session_id = s.session_id) AS decisions,
       (SELECT count(*) FROM conflict c
          JOIN belief b ON c.belief_id_1 = b.belief_id
         WHERE b.agent_id IN (SELECT agent_id FROM agent_session
                               WHERE session_id = s.session_id)) AS conflicts_involving_session_agents
  FROM session s
 WHERE s.session_id = 1;
