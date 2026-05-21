# MAMS — Multi-Agent Memory Store
## Database Schema (Stage 1 — DDL)

PostgreSQL 16 schema for the EN.605.641 term project.

### What this is
Three SQL scripts that build the 18-table MAMS database. The scripts
ARE the database — run them and you get an identical copy anywhere.

### One-time setup (macOS)
```bash
brew install postgresql@16
brew services start postgresql@16
createdb mams
```

### Build the schema
Run all three layers at once (recommended):
```bash
cd mams_sql
psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
```

Or run them individually, in this order (order matters — later
layers reference tables created by earlier ones):
```bash
psql -d mams -f 01_objective_layer.sql
psql -d mams -f 02_agent_layer.sql
psql -d mams -f 03_epistemic_layer.sql
```

### Verify it worked
```bash
psql -d mams -c '\dt'      # should list 18 tables
```

### Start over (if needed)
```bash
dropdb mams && createdb mams
psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
```

### The 18 tables, by layer

**Objective Layer** — ground truth of the world
world, location, character, character_relationship,
character_location, event, relationship_type, event_type

**Agent Layer** — the AI system
agent, agent_type, agent_character, session,
agent_session, decision

**Epistemic Layer** — what agents believe
memory, belief, knowledge_event, conflict

### Status
- [x] Stage 1 — Schema / DDL (this package)
- [ ] Stage 2 — Seed data
- [ ] Stage 3 — Triggers, stored procedures, functions
- [ ] Stage 4 — Queries
- [ ] Stage 5 — ERD

### Notes
- ITEM and ITEM_LOCATION were cut from the original 21-entity design
  (zero CRUD operations — see project report Section 5).
- MAMS is audit-first: no DELETE operations. Records are superseded
  or marked inactive, never removed.
