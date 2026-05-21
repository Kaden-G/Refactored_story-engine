# MAMS — Multi-Agent Memory Store
## PostgreSQL Database — EN.605.641 Term Project

A relational database giving multi-agent AI systems persistent,
queryable, conflict-aware memory. Test world: **Greywatch**.

### One-time setup (macOS)
```bash
brew install postgresql@16
brew services start postgresql@16
createdb mams
```

### Build everything
```bash
cd mams_sql
psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
```
This builds 18 tables, installs 9 SQL features (3 functions,
3 procedures, 3 triggers), and loads the Greywatch seed world.

### Run the 10 queries
```bash
psql -d mams -f 08_queries.sql
```

### Start over
```bash
dropdb mams && createdb mams
psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
```

### Files
| File | Purpose |
|---|---|
| 00_run_all.sql | Runs everything in the correct order |
| 01_objective_layer.sql | 8 tables — world, locations, characters, events |
| 02_agent_layer.sql | 6 tables — agents, sessions, decisions |
| 03_epistemic_layer.sql | 4 tables — memory, belief, knowledge, conflict |
| 04_seed_data.sql | The Greywatch test world |
| 05_functions.sql | 3 read-only functions |
| 06_procedures.sql | 3 stored procedures |
| 07_triggers.sql | 3 triggers (incl. auto conflict detection) |
| 08_queries.sql | The 10 demonstration queries |

### The 18 tables, by layer
**Objective** — world, location, character, character_relationship,
character_location, event, relationship_type, event_type
**Agent** — agent, agent_type, agent_character, session,
agent_session, decision
**Epistemic** — memory, belief, knowledge_event, conflict

### SQL features
**Functions**: get_conflict_count, get_location_occupants, get_agent_belief
**Procedures**: start_session, propagate_event, resolve_conflict
**Triggers**: trg_detect_conflict (auto-flags contradicting beliefs),
trg_touch_memory, trg_guard_session_status (finished sessions immutable)

### Project status
- [x] Stage 1 — Schema / DDL (18 tables)
- [x] Stage 2 — Seed data (Greywatch world)
- [x] Stage 3 — Functions, procedures, triggers (9 objects)
- [x] Stage 4 — Queries (10 queries)
- [ ] Stage 5 — ERD

### Notes
- ITEM and ITEM_LOCATION were cut from the original 21-entity
  design (zero CRUD operations — see project report Section 5).
- MAMS is audit-first: no DELETE operations anywhere. Records are
  superseded or marked inactive, never removed.
- Requires PostgreSQL 16+ (uses recursive CTEs, GENERATED IDENTITY,
  PL/pgSQL triggers and procedures).
