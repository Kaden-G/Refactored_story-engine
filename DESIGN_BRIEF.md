# story-engine v2 — Design Brief

> **Purpose of this document.** This is a handoff brief for building the
> application layers of story-engine v2 on top of the MAMS database. The
> database is already designed, built, and tested. This document explains
> what MAMS is, what already exists, and the architecture for the two
> layers still to build: a Python data-access layer and a LangGraph
> orchestration layer.

---

## 1. Context

**story-engine** is a multi-agent AI system that generates and maintains a
narrative. Multiple agents collaborate: a Director orchestrates specialist
agents (Writer, Lore-keeper) and NPC agents that portray individual
characters.

**story-engine v1** was a hodgepodge of agents with no shared persistent
memory. Agents forgot context, contradicted each other and earlier
decisions, had no shared world-state, and there was no way to track which
agent decided what. v2 is a deliberate refactor onto two foundations:

- **LangGraph** for orchestration (control flow, which agent runs when).
- **MAMS** for memory (persistent, queryable, conflict-aware state).

This document assumes the MAMS database exists. It does — see Section 3.

---

## 2. What MAMS is

**MAMS (Multi-Agent Memory Store)** is a PostgreSQL database that gives a
multi-agent system persistent, structured, conflict-aware memory.

The core idea, in four steps:

1. **Something happens** in the world (an event).
2. **The database records who witnessed it** — based on character location.
3. **Each agent forms its own belief** about it. Different agents can hold
   different, even contradictory, beliefs. This is *information asymmetry*
   and it is intentional.
4. **The database detects when two beliefs contradict** and flags a conflict
   — automatically, via a trigger.

Step 4 is the thesis: a flat file can store steps 1–3 but cannot *detect*
contradiction across agents. A relational database can.

### The two-layer memory model

MAMS separates two things most memory systems conflate:

- **Objective layer** — ground truth. What actually happened in the world.
- **Epistemic layer** — what each agent *believes* is true. May diverge
  from objective truth and from other agents.

An agent can believe the king is alive while the objective record says he
is dead, because nobody told that agent yet. Both records are valid.

---

## 3. What already exists (the MAMS database)

A complete PostgreSQL 16 database, delivered as 8 SQL scripts in `mams_sql/`.
Running `00_run_all.sql` builds everything from scratch.

### Schema — 18 tables in 3 layers

**Objective layer (8 tables)**
`world`, `location`, `character`, `character_relationship`,
`character_location`, `event`, `relationship_type`, `event_type`

**Agent layer (6 tables)**
`agent`, `agent_type`, `agent_character`, `session`, `agent_session`,
`decision`

**Epistemic layer (4 tables)**
`memory`, `belief`, `knowledge_event`, `conflict`

Notable design points:
- Primary keys are `GENERATED ALWAYS AS IDENTITY` (database assigns IDs).
- `location` is self-referencing (`parent_location_id`) — a hierarchy:
  World > Region > Building > Room > Point — plus grid coordinates.
- `character` and `agent` are deliberately separate. A character is a
  narrative entity (person, weather, crowd). An agent is an AI instance.
  Some agents portray a character; the Director and Lore-keeper do not.
- `belief` is polymorphic: `subject_type` + `subject_id` lets a belief be
  about a character, relationship, event, location, or world_state.
- `belief.superseded_by` is a self-referencing FK — beliefs form a history
  chain rather than being overwritten.
- MAMS is **audit-first**: no DELETE anywhere. Records are superseded or
  marked inactive, never removed.
- `ITEM` and `ITEM_LOCATION` are designed in the conceptual model but NOT
  implemented yet — they are reserved for future inventory tracking.

### SQL features (9 objects, all tested)

**Functions** (read-only)
- `get_conflict_count(agent_id)` — count of unresolved conflicts for an agent
- `get_location_occupants(location_id, at_time)` — characters at a place/time
- `get_agent_belief(agent_id, subject_type, subject_id)` — an agent's
  current beliefs about a subject

**Stored procedures** (multi-step writes)
- `start_session(world_id, director_agent_id, narrative_context)` — opens a
  session, enrolls all active agents; returns new session_id
- `propagate_event(event_id)` — distributes event knowledge to agents whose
  character was present; logs a decision
- `resolve_conflict(conflict_id, winning_belief_id, resolving_agent_id,
  rationale)` — supersedes the losing belief, logs a decision, stamps the
  conflict resolved

**Triggers** (automatic reactions)
- `trg_detect_conflict` — AFTER INSERT on `belief`; auto-flags high-confidence
  (>= 0.70) competing beliefs about the same subject from different agents as
  a `conflict` row. Conservative by design: the DB surfaces *candidate*
  conflicts; an agent or human confirms semantic contradiction.
- `trg_touch_memory` — BEFORE UPDATE on `memory`; refreshes `last_accessed_at`
- `trg_guard_session_status` — BEFORE UPDATE on `session`; finished sessions
  are immutable; auto-stamps `ended_at`

### Seed data — the "Greywatch" test world

A curated multi-agent narrative: 1 world, 5 locations, 7 characters,
5 agents, 3 events, beliefs, and one seeded conflict. Built specifically to
exercise information asymmetry — e.g. one agent deliberately does NOT know
about a key event because its character was not present.

### The session model

A `session` = one complete Director loop. This is the key alignment point
with LangGraph: **one LangGraph run should equal one MAMS session.** The
Director starts a session, agents work, the session ends, memory is
extracted. LangGraph carries live run-state; MAMS carries durable state.

---

## 4. What to build (the two new layers)

The architecture is three layers. The bottom one exists. Build the other two.

```
  LangGraph orchestration layer   <-- TO BUILD (Section 4.2)
            |
            v  calls
  Python data-access layer        <-- TO BUILD (Section 4.1)
            |
            v  psycopg
  MAMS database (PostgreSQL)       <-- EXISTS
```

### Design principle (important)

Keep the **memory logic in the database** — the triggers, procedures, and
conflict detection. Keep the **orchestration logic in LangGraph**. The
Python layer is a thin bridge, not a place for business logic.

Rationale: MAMS is the durable, owned asset. If epistemic logic leaks into
LangGraph-specific node code, swapping or upgrading the orchestrator later
means losing it. The database is the thing that should outlive framework
choices.

### 4.1 Python data-access layer

A thin module that wraps MAMS. Suggested: `psycopg` (version 3) as the
PostgreSQL driver. This layer should:

- Manage connections (a connection pool is appropriate).
- Expose one Python function per MAMS operation the application needs.
  Each maps to a procedure, function, or query — e.g.
  `start_session(...)`, `propagate_event(event_id)`,
  `get_agent_belief(...)`, `resolve_conflict(...)`,
  plus the 10 queries from `08_queries.sql` as needed.
- Use **parameterized queries only** — never string-formatted SQL.
- Return plain Python data structures (dicts / dataclasses), not raw
  cursor rows, so the LangGraph layer never sees the database.
- Contain **no narrative or orchestration logic** — it only reads and
  writes MAMS.

Open question for the next session: dataclasses vs. an ORM (e.g.
SQLAlchemy). A thin dataclass mapping is likely enough and keeps the SQL
visible; an ORM adds abstraction that may not be worth it here. Decide
early.

### 4.2 LangGraph orchestration layer

The Director/worker graph. This layer should:

- Model the Director loop as a LangGraph `StateGraph`.
- At the **start** of a run, call the Python layer's `start_session(...)`
  and hydrate run-state from MAMS (recent memory, current beliefs, world
  state).
- During the run, when events occur, call `propagate_event(...)`; when
  agents form conclusions, write `belief` rows (the trigger handles
  conflict detection automatically).
- At the **end** of a run, extract durable memory into `memory` rows and
  close the session.
- Treat the LangGraph state object as ephemeral working memory for one
  run only. Anything that must survive the run goes to MAMS.

Open question for the next session: how much state lives in the LangGraph
checkpoint vs. MAMS. Recommendation: LangGraph checkpoints handle
within-run resumability; MAMS is the cross-run source of truth. Do not
duplicate durable state into checkpoints.

---

## 5. Suggested build order

1. Stand up MAMS locally (`brew install postgresql@16`, `createdb mams`,
   run `00_run_all.sql`). Confirm with `08_queries.sql`.
2. Build the Python data-access layer (4.1). Start with `start_session`,
   `propagate_event`, and a few read queries. Unit-test against the
   Greywatch seed data — the expected results are known and stable.
3. Build a minimal LangGraph graph (4.2): one Director loop that opens a
   session, runs one trivial step, and closes it. Prove the round trip.
4. Expand: real specialist and NPC agents, belief writes, the full loop.
5. Replace or augment the Greywatch seed world with live story content.

Do not start at step 3. The Python layer must exist first or LangGraph has
nothing correct to call.

---

## 6. Reference: files in `mams_sql/`

| File | Contents |
|---|---|
| `00_run_all.sql` | Master script — builds everything in order |
| `01_objective_layer.sql` | DDL — 8 objective-layer tables |
| `02_agent_layer.sql` | DDL — 6 agent-layer tables |
| `03_epistemic_layer.sql` | DDL — 4 epistemic-layer tables |
| `04_seed_data.sql` | The Greywatch test world |
| `05_functions.sql` | 3 functions |
| `06_procedures.sql` | 3 stored procedures |
| `07_triggers.sql` | 3 triggers |
| `08_queries.sql` | 10 demonstration queries |

To rebuild from scratch at any time:

```bash
dropdb mams && createdb mams
psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
```

---

## 7. Scope guardrails for the next session

- The MAMS **database is done**. Do not redesign the schema mid-build. If a
  schema change is genuinely needed, add a new numbered migration script
  (`09_...sql`) — never edit the existing ones.
- Build the **Python layer before the LangGraph layer**.
- Keep memory logic in SQL, orchestration logic in LangGraph, and nothing
  but a thin bridge in between.
- `ITEM` / `ITEM_LOCATION` implementation is deferred — only build them when
  inventory is genuinely needed, as their own migration.
- This is the story-engine project, separate from the database course
  project. Track it separately.

---

*Document generated as a handoff brief. The MAMS database it describes was
designed, built, and tested in a prior session. Schema, seed data, SQL
features, and queries are all complete and verified on PostgreSQL 16.*
