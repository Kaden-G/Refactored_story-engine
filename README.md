# story-engine v2

A multi-agent AI system that generates and maintains a narrative.
Multiple agents collaborate — a **Director** orchestrates specialist agents
(**Writer**, **Lore-keeper**) and **NPC agents** that portray individual
characters — all backed by persistent, conflict-aware memory.

Built on two foundations:
- **MAMS** (Multi-Agent Memory Store) — a PostgreSQL database that gives
  the agent system persistent, structured, conflict-aware memory.
- **LangGraph** — orchestration framework that models the Director loop
  as a state graph.

---

## Architecture

```
  LangGraph orchestration layer    story_engine/orchestration/
            │
            ▼  calls
  Python data-access layer         story_engine/dal/
            │
            ▼  psycopg 3
  MAMS database (PostgreSQL 16)    *.sql
```

**Design principle:** Memory logic lives in the database (triggers,
procedures, conflict detection). Orchestration logic lives in LangGraph.
The Python layer is a thin bridge — no business logic.

---

## Quick start

### 1. Install PostgreSQL 16 and seed the database
```bash
createdb mams
psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
```

### 2. Install Python dependencies
```bash
pip install -e ".[dev]"
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your DB credentials and (optionally) ANTHROPIC_API_KEY
```

### 4. Run the test suite
```bash
pytest tests/ -v
```

### 5. Run a Director session
```bash
python run_session.py
```
Without an `ANTHROPIC_API_KEY`, all agents use rule-based fallbacks —
useful for proving the full round-trip works. With a key, agents use
Claude for generation.

### Reset the database
```bash
dropdb mams && createdb mams
psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
```

---

## Project structure

```
├── 00_run_all.sql                  Master build script
├── 01_objective_layer.sql          8 tables — world, locations, characters, events
├── 02_agent_layer.sql              6 tables — agents, sessions, decisions
├── 03_epistemic_layer.sql          4 tables — memory, belief, knowledge, conflict
├── 04_seed_data.sql                Greywatch test world (7 characters, 5 agents)
├── 05_functions.sql                3 read-only functions
├── 06_procedures.sql               3 stored procedures
├── 07_triggers.sql                 3 triggers (incl. auto conflict detection)
├── 08_queries.sql                  10 demonstration queries
│
├── story_engine/
│   ├── dal/                        Python data-access layer
│   │   ├── models.py               24 frozen dataclasses (18 tables + 6 composites)
│   │   ├── connection.py           psycopg 3 connection pool, env-var config
│   │   └── mams_dal.py             MamsDAL class (~45 methods)
│   │
│   └── orchestration/              LangGraph orchestration layer
│       ├── state.py                StoryState TypedDict + AgentContext
│       ├── prompts.py              System prompts for all agent roles
│       ├── nodes.py                Node factories (8 nodes)
│       └── graph.py                build_director_graph() — compiles the StateGraph
│
├── tests/
│   ├── conftest.py                 Session-scoped fixtures for Greywatch
│   └── test_dal.py                 ~25 test cases against seed data
│
├── run_session.py                  CLI entry point for a full session
├── pyproject.toml                  Package config (story-engine 2.0.0a1)
├── requirements.txt                Pinned dependencies
└── .env.example                    Environment variable template
```

---

## MAMS database

### The two-layer memory model
MAMS separates what most memory systems conflate:
- **Objective layer** — ground truth. What actually happened.
- **Epistemic layer** — what each agent *believes*. May diverge from
  truth and from other agents. This is intentional information asymmetry.

### 18 tables across 3 layers

| Layer | Tables |
|---|---|
| **Objective** | world, location, character, character_relationship, character_location, event, relationship_type, event_type |
| **Agent** | agent, agent_type, agent_character, session, agent_session, decision |
| **Epistemic** | memory, belief, knowledge_event, conflict |

### 9 SQL features

| Type | Name | Purpose |
|---|---|---|
| Function | `get_conflict_count` | Unresolved conflicts for an agent |
| Function | `get_location_occupants` | Characters at a place/time |
| Function | `get_agent_belief` | Agent's current beliefs about a subject |
| Procedure | `start_session` | Opens session, enrolls all active agents |
| Procedure | `propagate_event` | Distributes event knowledge by location |
| Procedure | `resolve_conflict` | Supersedes losing belief, logs decision |
| Trigger | `trg_detect_conflict` | Auto-flags contradicting high-confidence beliefs |
| Trigger | `trg_touch_memory` | Refreshes last_accessed_at on memory update |
| Trigger | `trg_guard_session_status` | Finished sessions are immutable |

---

## LangGraph orchestration

### Director loop (one run = one MAMS session)

```
open_session → director_plan → route_agent → { writer | lorekeeper | npc }
                    ▲                                       │
                    │                                       ▼
                    │                               process_events
                    │                                       │
                    │                                       ▼
                    └──── (loop if not done) ──── process_beliefs
                                                            │
                                                     close_session → END
```

### Agent roles
- **Director** — orchestrator. Decides which agent acts next and what
  narrative beat to pursue. Outputs structured JSON.
- **Writer** — specialist. Generates narrative prose. Does not decide plot.
- **Lore-keeper** — specialist. Guards continuity, adjudicates belief
  conflicts, provides lore context.
- **NPC agents** — each portrays one character. Speaks in first person.
  Only knows what MAMS says it knows (information asymmetry enforced).

---

## Session model

A `session` = one complete Director loop.

**One LangGraph run = one MAMS session.**

- LangGraph carries ephemeral working memory (the `StoryState`).
- MAMS carries durable state (beliefs, memories, conflicts, audit trail).
- At session open: hydrate from MAMS.
- During the run: write events, beliefs, decisions to MAMS.
- At session close: extract memories, close session. MAMS persists everything.

---

## Build status

- [x] MAMS database (18 tables, 9 SQL features, seed data)
- [x] Python data-access layer (MamsDAL, ~45 methods)
- [x] LangGraph orchestration (Director loop, 8 nodes, agent routing)
- [x] Agent prompts (Director, Writer, Lore-keeper, NPC)
- [x] Test suite (~25 tests against Greywatch seed data)
- [ ] Live testing with PostgreSQL + Claude
- [ ] Augment Greywatch with live story content

---

## Design notes

- **Audit-first**: no DELETE anywhere. Records are superseded or marked
  inactive, never removed.
- **Schema is frozen**: never edit existing SQL files. Add new numbered
  migration scripts (`09_*.sql`) if schema changes are needed.
- **ITEM / ITEM_LOCATION**: designed but not yet implemented — reserved
  for future inventory tracking.
- Requires **PostgreSQL 16+** and **Python 3.11+**.
