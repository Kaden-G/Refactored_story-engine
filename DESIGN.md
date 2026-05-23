# story-engine v2 — Complete Technical Specification

> **How to use this document.**
> This is the full end-state technical spec for story-engine v2. It is
> structured as numbered build phases and steps. Point Claude Code at a
> single step (e.g. "build Phase 1, Step 1.4 — session_ops.py") and it
> has everything it needs. Complete Phase 1 entirely before starting
> Phase 2. Do not skip steps.
>
> **What exists:** The MAMS PostgreSQL 16 database (`mams_sql/`), fully
> built and tested. All schema, seed data, functions, procedures,
> triggers, and queries are complete.
>
> **What to build:** Phase 1 — Python data-access layer. Phase 2 —
> LangGraph orchestration layer.

---

## Architecture

```
  ┌─────────────────────────────────────────┐
  │        LangGraph orchestration          │  Phase 2
  │  (Director graph + agent nodes)         │
  └────────────────┬────────────────────────┘
                   │ imports
  ┌────────────────▼────────────────────────┐
  │        Python data-access layer         │  Phase 1
  │  story_engine/mams/  (thin bridge)      │
  └────────────────┬────────────────────────┘
                   │ psycopg3
  ┌────────────────▼────────────────────────┐
  │        MAMS — PostgreSQL 16             │  EXISTS
  │  mams_sql/  (schema + procedures)       │
  └─────────────────────────────────────────┘
```

**Core constraint:** Memory logic lives in the database. Orchestration
logic lives in LangGraph. The Python layer is a thin bridge with no
business logic of its own.

---

## Repository layout

```
Refactored_story-engine/
├── mams_sql/                        # READ-ONLY — do not edit
│   ├── 00_run_all.sql
│   ├── 01_objective_layer.sql
│   ├── 02_agent_layer.sql
│   ├── 03_epistemic_layer.sql
│   ├── 04_seed_data.sql
│   ├── 05_functions.sql
│   ├── 06_procedures.sql
│   ├── 07_triggers.sql
│   └── 08_queries.sql
├── story_engine/
│   ├── __init__.py
│   ├── mams/                        # Phase 1
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── exceptions.py
│   │   ├── models.py
│   │   ├── session_ops.py
│   │   ├── event_ops.py
│   │   ├── belief_ops.py
│   │   ├── conflict_ops.py
│   │   └── queries.py
│   └── graph/                       # Phase 2
│       ├── __init__.py
│       ├── state.py
│       ├── graph.py
│       ├── nodes/
│       │   ├── __init__.py
│       │   ├── director.py
│       │   ├── writer.py
│       │   ├── lore_keeper.py
│       │   ├── npc.py
│       │   ├── events.py
│       │   ├── beliefs.py
│       │   └── conflict.py
│       └── prompts/
│           ├── director.py
│           ├── writer.py
│           ├── lore_keeper.py
│           ├── npc.py
│           └── conflict.py
├── tests/
│   ├── conftest.py
│   ├── phase1/
│   │   ├── test_connection.py
│   │   ├── test_session_ops.py
│   │   ├── test_event_ops.py
│   │   ├── test_belief_ops.py
│   │   ├── test_conflict_ops.py
│   │   └── test_queries.py
│   └── phase2/
│       ├── test_graph_roundtrip.py
│       └── test_full_session.py
├── .env.example
├── .env                             # gitignored
├── pyproject.toml
└── README.md
```

---

## `pyproject.toml`

```toml
[project]
name = "story-engine"
version = "0.2.0"
requires-python = ">=3.12"
dependencies = [
    "psycopg[binary]>=3.2",
    "psycopg-pool>=3.2",
    "python-dotenv>=1.2",
    "langgraph>=0.2",
    "langchain-anthropic>=0.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-dotenv>=0.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
env_files = [".env"]
```

## `.env.example`

```
MAMS_DSN=postgresql://localhost:5432/mams
ANTHROPIC_API_KEY=sk-ant-...
STORY_ENGINE_MODEL=claude-sonnet-4-20250514
STORY_ENGINE_MAX_TURNS=10
```

---

# PHASE 1 — Python Data-Access Layer

Build steps 1.0 → 1.8 in order. Run `pytest tests/phase1/` after each
step before proceeding to the next.

---

## Step 1.0 — Project bootstrap

**Goal:** Empty project that installs and has a passing (zero-test) pytest run.

```bash
# From repo root
pip install -e ".[dev]"
touch story_engine/__init__.py
touch story_engine/mams/__init__.py
pytest  # should collect 0 items, exit 0
```

`story_engine/mams/__init__.py` re-exports the full public API once all
modules exist. Leave it empty until Step 1.8, then populate:

```python
from .connection import init_pool, get_conn
from .exceptions import (
    MAMSError, MAMSConnectionError, MAMSNotFoundError,
    MAMSConstraintError, MAMSSessionLockedError,
)
from .models import (
    SessionInfo, AgentInfo, CharacterInfo, Belief,
    Conflict, KnowledgeEvent, Decision, WorldState, TimelineEntry,
)
from .session_ops import start_session, close_session, get_session, get_active_agents
from .event_ops import create_event, propagate_event
from .belief_ops import write_belief, get_agent_belief
from .conflict_ops import get_conflict_count, get_unresolved_conflicts, resolve_conflict
from . import queries
```

---

## Step 1.1 — `connection.py` + `exceptions.py`

**Goal:** Pool initialisation and the error hierarchy. Everything else
depends on these two files.

### `story_engine/mams/exceptions.py`

```python
class MAMSError(Exception):
    """Base class for all MAMS data-access errors.
    LangGraph nodes should only catch MAMSError — never psycopg.*"""

class MAMSConnectionError(MAMSError):
    """Pool not initialised, or database unreachable."""

class MAMSNotFoundError(MAMSError):
    """A required record was not found."""
    def __init__(self, entity: str, id_: int | str):
        super().__init__(f"{entity} '{id_}' not found")
        self.entity = entity
        self.id = id_

class MAMSConstraintError(MAMSError):
    """A DB constraint was violated (FK, unique, check).
    Wraps psycopg.errors.IntegrityError."""

class MAMSSessionLockedError(MAMSError):
    """Attempted to write to a completed or abandoned session.
    Raised when trg_guard_session_status rejects an update."""
```

### `story_engine/mams/connection.py`

```python
from __future__ import annotations
from contextlib import contextmanager
from typing import Generator
import os

from psycopg_pool import ConnectionPool
from psycopg import Connection

from .exceptions import MAMSConnectionError

_pool: ConnectionPool | None = None


def init_pool(
    dsn: str | None = None,
    min_size: int = 2,
    max_size: int = 10,
) -> None:
    """Initialise the connection pool. Call once at application startup.
    Reads MAMS_DSN from environment if dsn is not provided."""
    global _pool
    resolved_dsn = dsn or os.environ.get("MAMS_DSN")
    if not resolved_dsn:
        raise MAMSConnectionError(
            "No DSN provided and MAMS_DSN is not set in environment"
        )
    _pool = ConnectionPool(
        resolved_dsn,
        min_size=min_size,
        max_size=max_size,
        open=True,
    )


def close_pool() -> None:
    """Cleanly close the pool. Call on application shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn() -> Generator[Connection, None, None]:
    """Yield a connection from the pool.
    Commits on clean exit, rolls back on any exception."""
    if _pool is None:
        raise MAMSConnectionError(
            "Connection pool is not initialised. Call init_pool() first."
        )
    with _pool.connection() as conn:
        yield conn
```

### `tests/conftest.py`

```python
import os
import pytest
from dotenv import load_dotenv
from story_engine.mams.connection import init_pool, close_pool

# Greywatch seed data constants — read exact IDs from 04_seed_data.sql
# and fill these in. They are stable; the seed never changes.
GREYWATCH_WORLD_ID: int = 1          # fill from seed
GREYWATCH_DIRECTOR_AGENT_ID: int = 1 # fill from seed
GREYWATCH_NPC_AGENT_IDS: list[int] = []  # fill from seed (non-director agents)
GREYWATCH_LOCATION_IDS: list[int] = []   # fill from seed
GREYWATCH_CHARACTER_IDS: list[int] = []  # fill from seed
GREYWATCH_EVENT_IDS: list[int] = []      # fill from seed (the 3 events)
GREYWATCH_SEEDED_CONFLICT_ID: int = 1    # fill from seed


@pytest.fixture(scope="session", autouse=True)
def db_pool():
    load_dotenv()
    init_pool()
    yield
    close_pool()
```

### `tests/phase1/test_connection.py`

```python
import pytest
from story_engine.mams.connection import get_conn
from story_engine.mams.exceptions import MAMSConnectionError


def test_pool_smoke(db_pool):
    """Pool is up and the database responds."""
    with get_conn() as conn:
        result = conn.execute("SELECT 1 AS ok").fetchone()
    assert result is not None
    assert result[0] == 1


def test_get_conn_without_pool_raises():
    """get_conn() without init_pool() raises MAMSConnectionError.
    This test intentionally bypasses the session fixture."""
    import story_engine.mams.connection as c
    original = c._pool
    c._pool = None
    try:
        with pytest.raises(MAMSConnectionError):
            with c.get_conn():
                pass
    finally:
        c._pool = original
```

---

## Step 1.2 — `models.py`

**Goal:** All dataclasses used as return types. No logic — pure data.

### `story_engine/mams/models.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SessionInfo:
    session_id: int
    world_id: int
    director_agent_id: int
    narrative_context: str
    status: str                  # 'active' | 'completed' | 'abandoned'
    started_at: datetime
    ended_at: datetime | None


@dataclass
class AgentInfo:
    agent_id: int
    name: str
    agent_type: str              # 'director' | 'specialist' | 'npc'
    is_active: bool


@dataclass
class CharacterInfo:
    character_id: int
    name: str
    location_id: int | None
    is_active: bool


@dataclass
class Belief:
    belief_id: int
    agent_id: int
    subject_type: str            # 'character' | 'relationship' | 'event' |
                                 #   'location' | 'world_state'
    subject_id: int
    content: str
    confidence: float            # 0.0 – 1.0
    superseded_by: int | None    # belief_id of superseding belief, if any
    created_at: datetime


@dataclass
class Conflict:
    conflict_id: int
    belief_a_id: int
    belief_b_id: int
    status: str                  # 'open' | 'resolved'
    detected_at: datetime
    resolved_at: datetime | None
    resolving_agent_id: int | None
    rationale: str | None


@dataclass
class KnowledgeEvent:
    knowledge_event_id: int
    agent_id: int
    event_id: int
    received_at: datetime


@dataclass
class Decision:
    decision_id: int
    session_id: int
    agent_id: int
    decision_type: str
    rationale: str | None
    created_at: datetime


@dataclass
class WorldState:
    world_id: int
    name: str
    description: str | None


@dataclass
class TimelineEntry:
    event_id: int
    description: str
    location_id: int | None
    occurred_at: datetime


@dataclass
class LocationOccupant:
    character_id: int
    name: str
    arrived_at: datetime
```

---

## Step 1.3 — `session_ops.py`

**Goal:** Session lifecycle — open, close, read.

### `story_engine/mams/session_ops.py`

```python
from __future__ import annotations
from datetime import datetime

import psycopg

from .connection import get_conn
from .exceptions import MAMSNotFoundError, MAMSSessionLockedError, MAMSConstraintError
from .models import SessionInfo, AgentInfo


def start_session(
    world_id: int,
    director_agent_id: int,
    narrative_context: str,
) -> SessionInfo:
    """Call the MAMS start_session stored procedure.
    Opens a session and enrolls all active agents.
    Returns the newly created SessionInfo."""
    with get_conn() as conn:
        try:
            conn.execute(
                "CALL start_session(%s, %s, %s)",
                (world_id, director_agent_id, narrative_context),
            )
            # start_session inserts the session row; fetch it back.
            # The procedure returns session_id via an OUT param or we
            # query the most recent session for this director.
            # Adjust query to match actual procedure output signature.
            row = conn.execute(
                """
                SELECT session_id, world_id, director_agent_id,
                       narrative_context, status, started_at, ended_at
                FROM session
                WHERE director_agent_id = %s
                  AND status = 'active'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (director_agent_id,),
            ).fetchone()
        except psycopg.errors.IntegrityError as e:
            raise MAMSConstraintError(str(e)) from e

    if row is None:
        raise MAMSNotFoundError("session", f"director_agent_id={director_agent_id}")

    return SessionInfo(
        session_id=row[0],
        world_id=row[1],
        director_agent_id=row[2],
        narrative_context=row[3],
        status=row[4],
        started_at=row[5],
        ended_at=row[6],
    )


def close_session(session_id: int) -> None:
    """Set session status to 'completed'.
    The trg_guard_session_status trigger stamps ended_at automatically.
    Raises MAMSSessionLockedError if session is already finished."""
    with get_conn() as conn:
        try:
            conn.execute(
                "UPDATE session SET status = 'completed' WHERE session_id = %s",
                (session_id,),
            )
        except psycopg.errors.RaiseException as e:
            # Guard trigger raises when session already finished
            raise MAMSSessionLockedError(str(e)) from e


def get_session(session_id: int) -> SessionInfo:
    """Fetch a session by ID.
    Raises MAMSNotFoundError if not found."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT session_id, world_id, director_agent_id,
                   narrative_context, status, started_at, ended_at
            FROM session
            WHERE session_id = %s
            """,
            (session_id,),
        ).fetchone()

    if row is None:
        raise MAMSNotFoundError("session", session_id)

    return SessionInfo(
        session_id=row[0],
        world_id=row[1],
        director_agent_id=row[2],
        narrative_context=row[3],
        status=row[4],
        started_at=row[5],
        ended_at=row[6],
    )


def get_active_agents(session_id: int) -> list[AgentInfo]:
    """Return all agents enrolled in a session via agent_session."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT a.agent_id, a.name, at.name AS agent_type, a.is_active
            FROM agent_session ase
            JOIN agent a ON a.agent_id = ase.agent_id
            JOIN agent_type at ON at.agent_type_id = a.agent_type_id
            WHERE ase.session_id = %s
              AND a.is_active = TRUE
            ORDER BY a.agent_id
            """,
            (session_id,),
        ).fetchall()

    return [
        AgentInfo(
            agent_id=r[0],
            name=r[1],
            agent_type=r[2],
            is_active=r[3],
        )
        for r in rows
    ]
```

### `tests/phase1/test_session_ops.py`

```python
import pytest
from story_engine.mams import session_ops
from story_engine.mams.exceptions import MAMSSessionLockedError
from story_engine.mams.models import SessionInfo
from tests.conftest import GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID


@pytest.fixture
def open_session(db_pool):
    s = session_ops.start_session(
        world_id=GREYWATCH_WORLD_ID,
        director_agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        narrative_context="pytest: test session",
    )
    yield s
    # Cleanup: ensure session is closed even if test fails
    try:
        session_ops.close_session(s.session_id)
    except MAMSSessionLockedError:
        pass  # Already closed by the test


def test_start_session_returns_sessioninfo(open_session):
    s = open_session
    assert isinstance(s, SessionInfo)
    assert s.status == "active"
    assert s.world_id == GREYWATCH_WORLD_ID
    assert s.director_agent_id == GREYWATCH_DIRECTOR_AGENT_ID
    assert s.session_id > 0
    assert s.ended_at is None


def test_get_session_round_trips(open_session):
    fetched = session_ops.get_session(open_session.session_id)
    assert fetched.session_id == open_session.session_id
    assert fetched.status == "active"


def test_close_session_sets_completed(open_session):
    session_ops.close_session(open_session.session_id)
    fetched = session_ops.get_session(open_session.session_id)
    assert fetched.status == "completed"
    assert fetched.ended_at is not None


def test_double_close_raises_locked(open_session):
    session_ops.close_session(open_session.session_id)
    with pytest.raises(MAMSSessionLockedError):
        session_ops.close_session(open_session.session_id)


def test_get_active_agents_returns_agents(open_session):
    agents = session_ops.get_active_agents(open_session.session_id)
    assert len(agents) >= 1
    agent_types = {a.agent_type for a in agents}
    assert "director" in agent_types  # Greywatch always has a director
```

---

## Step 1.4 — `event_ops.py`

**Goal:** Create events and propagate them to agents.

### `story_engine/mams/event_ops.py`

```python
from __future__ import annotations
from datetime import datetime

import psycopg

from .connection import get_conn
from .exceptions import MAMSConstraintError, MAMSNotFoundError


def create_event(
    world_id: int,
    event_type_id: int,
    location_id: int,
    description: str,
    occurred_at: datetime | None = None,
) -> int:
    """Insert a new event row. Returns the new event_id.
    occurred_at defaults to now() in the database if not provided."""
    with get_conn() as conn:
        try:
            if occurred_at is not None:
                row = conn.execute(
                    """
                    INSERT INTO event
                        (world_id, event_type_id, location_id,
                         description, occurred_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING event_id
                    """,
                    (world_id, event_type_id, location_id,
                     description, occurred_at),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    INSERT INTO event
                        (world_id, event_type_id, location_id, description)
                    VALUES (%s, %s, %s, %s)
                    RETURNING event_id
                    """,
                    (world_id, event_type_id, location_id, description),
                ).fetchone()
        except psycopg.errors.IntegrityError as e:
            raise MAMSConstraintError(str(e)) from e

    if row is None:
        raise MAMSNotFoundError("event", "newly inserted")
    return row[0]


def propagate_event(event_id: int) -> None:
    """Call the MAMS propagate_event stored procedure.
    Distributes knowledge_event rows to agents whose character was
    present at the event location. Logs a decision row."""
    with get_conn() as conn:
        conn.execute("CALL propagate_event(%s)", (event_id,))
```

### `tests/phase1/test_event_ops.py`

```python
import pytest
from story_engine.mams import event_ops, session_ops
from story_engine.mams.connection import get_conn
from story_engine.mams.exceptions import MAMSSessionLockedError
from tests.conftest import (
    GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID,
    GREYWATCH_LOCATION_IDS, GREYWATCH_EVENT_IDS,
    GREYWATCH_NPC_AGENT_IDS,
)

# Fill EVENT_TYPE_ID from 04_seed_data.sql — use any valid event type
VALID_EVENT_TYPE_ID = 1  # fill from seed data


@pytest.fixture
def session(db_pool):
    s = session_ops.start_session(
        GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID, "event test"
    )
    yield s
    try:
        session_ops.close_session(s.session_id)
    except MAMSSessionLockedError:
        pass


def test_create_event_returns_id(session):
    eid = event_ops.create_event(
        world_id=GREYWATCH_WORLD_ID,
        event_type_id=VALID_EVENT_TYPE_ID,
        location_id=GREYWATCH_LOCATION_IDS[0],
        description="A test event occurred.",
    )
    assert isinstance(eid, int)
    assert eid > 0


def test_propagate_event_creates_knowledge_rows(session):
    """After propagation, agents whose characters were at the location
    should have a knowledge_event row. Use a Greywatch event whose
    expected knowledge distribution is known from 04_seed_data.sql."""
    event_id = GREYWATCH_EVENT_IDS[0]  # use the first seed event
    event_ops.propagate_event(event_id)

    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_event WHERE event_id = %s",
            (event_id,),
        ).fetchone()[0]

    # Greywatch has a known number of characters present at each event.
    # Fill expected_count from seed data analysis.
    expected_count = 0  # fill from 04_seed_data.sql
    assert count >= expected_count
```

---

## Step 1.5 — `belief_ops.py`

**Goal:** Write beliefs and read current beliefs.
Critical: `write_belief` does NOT detect conflicts — that is the
`trg_detect_conflict` trigger's job. Insert the row; let the DB react.

### `story_engine/mams/belief_ops.py`

```python
from __future__ import annotations
from datetime import datetime

import psycopg

from .connection import get_conn
from .exceptions import MAMSConstraintError, MAMSNotFoundError
from .models import Belief


def write_belief(
    agent_id: int,
    subject_type: str,
    subject_id: int,
    content: str,
    confidence: float,
    session_id: int,
) -> int:
    """Insert a belief row. Returns the new belief_id.

    IMPORTANT: The trg_detect_conflict trigger fires automatically on
    INSERT. Do not add conflict detection logic here. Insert the row;
    the database handles the rest.

    subject_type must be one of:
        'character', 'relationship', 'event', 'location', 'world_state'
    confidence must be between 0.0 and 1.0.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be 0.0–1.0, got {confidence}")

    valid_subject_types = {
        "character", "relationship", "event", "location", "world_state"
    }
    if subject_type not in valid_subject_types:
        raise ValueError(
            f"subject_type must be one of {valid_subject_types}, got {subject_type!r}"
        )

    with get_conn() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO belief
                    (agent_id, subject_type, subject_id,
                     content, confidence, session_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING belief_id
                """,
                (agent_id, subject_type, subject_id,
                 content, confidence, session_id),
            ).fetchone()
        except psycopg.errors.IntegrityError as e:
            raise MAMSConstraintError(str(e)) from e

    if row is None:
        raise MAMSNotFoundError("belief", "newly inserted")
    return row[0]


def get_agent_belief(
    agent_id: int,
    subject_type: str,
    subject_id: int,
) -> list[Belief]:
    """Call the MAMS get_agent_belief function.
    Returns all current (non-superseded) beliefs for this
    agent/subject combination, ordered by created_at DESC."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM get_agent_belief(%s, %s, %s)",
            (agent_id, subject_type, subject_id),
        ).fetchall()

    return [
        Belief(
            belief_id=r[0],
            agent_id=r[1],
            subject_type=r[2],
            subject_id=r[3],
            content=r[4],
            confidence=r[5],
            superseded_by=r[6],
            created_at=r[7],
        )
        for r in rows
    ]
```

### `tests/phase1/test_belief_ops.py`

```python
import pytest
from story_engine.mams import belief_ops, session_ops, conflict_ops
from story_engine.mams.connection import get_conn
from story_engine.mams.exceptions import MAMSConstraintError, MAMSSessionLockedError
from tests.conftest import (
    GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID,
    GREYWATCH_NPC_AGENT_IDS, GREYWATCH_CHARACTER_IDS,
)


@pytest.fixture
def session(db_pool):
    s = session_ops.start_session(
        GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID, "belief test"
    )
    yield s
    try:
        session_ops.close_session(s.session_id)
    except MAMSSessionLockedError:
        pass


def test_write_belief_returns_id(session):
    bid = belief_ops.write_belief(
        agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        subject_type="character",
        subject_id=GREYWATCH_CHARACTER_IDS[0],
        content="The character is alive and well.",
        confidence=0.9,
        session_id=session.session_id,
    )
    assert isinstance(bid, int)
    assert bid > 0


def test_get_agent_belief_returns_beliefs(session):
    char_id = GREYWATCH_CHARACTER_IDS[0]
    belief_ops.write_belief(
        agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        subject_type="character",
        subject_id=char_id,
        content="Character is in the north tower.",
        confidence=0.8,
        session_id=session.session_id,
    )
    beliefs = belief_ops.get_agent_belief(
        agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        subject_type="character",
        subject_id=char_id,
    )
    assert len(beliefs) >= 1
    assert any("north tower" in b.content for b in beliefs)


def test_high_confidence_competing_beliefs_trigger_conflict(session):
    """CRITICAL: Two agents writing contradictory high-confidence beliefs
    about the same subject should produce a conflict row automatically.
    This exercises trg_detect_conflict — the core DB feature."""
    assert len(GREYWATCH_NPC_AGENT_IDS) >= 2, (
        "Need at least 2 NPC agents in Greywatch to test conflict trigger"
    )
    char_id = GREYWATCH_CHARACTER_IDS[0]
    agent_a = GREYWATCH_NPC_AGENT_IDS[0]
    agent_b = GREYWATCH_NPC_AGENT_IDS[1]

    # Both agents believe different things about the same character
    # at confidence >= 0.70, which is the trigger threshold
    belief_ops.write_belief(
        agent_id=agent_a,
        subject_type="character",
        subject_id=char_id,
        content="The character is alive.",
        confidence=0.85,
        session_id=session.session_id,
    )
    belief_ops.write_belief(
        agent_id=agent_b,
        subject_type="character",
        subject_id=char_id,
        content="The character is dead.",
        confidence=0.85,
        session_id=session.session_id,
    )

    # Trigger should have created a conflict row
    with get_conn() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) FROM conflict c
            JOIN belief ba ON ba.belief_id = c.belief_a_id
            JOIN belief bb ON bb.belief_id = c.belief_b_id
            WHERE (ba.agent_id = %s OR bb.agent_id = %s)
              AND c.status = 'open'
            """,
            (agent_a, agent_a),
        ).fetchone()[0]

    assert count >= 1, "trg_detect_conflict did not fire as expected"


def test_low_confidence_beliefs_do_not_trigger_conflict(session):
    """Beliefs below 0.70 confidence should NOT trigger conflict detection."""
    char_id = GREYWATCH_CHARACTER_IDS[0]
    agent_a = GREYWATCH_NPC_AGENT_IDS[0]
    agent_b = GREYWATCH_NPC_AGENT_IDS[1]

    before_count_row = get_conn().__enter__().execute(
        "SELECT COUNT(*) FROM conflict WHERE status = 'open'"
    ).fetchone()
    # Use separate connection cleanly
    with get_conn() as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM conflict WHERE status = 'open'"
        ).fetchone()[0]

    belief_ops.write_belief(
        agent_id=agent_a, subject_type="character", subject_id=char_id,
        content="Maybe alive.", confidence=0.50, session_id=session.session_id,
    )
    belief_ops.write_belief(
        agent_id=agent_b, subject_type="character", subject_id=char_id,
        content="Maybe dead.", confidence=0.50, session_id=session.session_id,
    )

    with get_conn() as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM conflict WHERE status = 'open'"
        ).fetchone()[0]

    assert after == before, "Low-confidence beliefs incorrectly triggered a conflict"
```

---

## Step 1.6 — `conflict_ops.py`

**Goal:** Read and resolve conflicts.

### `story_engine/mams/conflict_ops.py`

```python
from __future__ import annotations

from .connection import get_conn
from .exceptions import MAMSNotFoundError
from .models import Conflict


def get_conflict_count(agent_id: int) -> int:
    """Call MAMS get_conflict_count function.
    Returns the number of unresolved conflicts for the given agent."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT get_conflict_count(%s)", (agent_id,)
        ).fetchone()
    return row[0] if row else 0


def get_unresolved_conflicts(agent_id: int) -> list[Conflict]:
    """Return all open conflicts involving this agent's beliefs."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.conflict_id, c.belief_a_id, c.belief_b_id,
                   c.status, c.detected_at, c.resolved_at,
                   c.resolving_agent_id, c.rationale
            FROM conflict c
            JOIN belief ba ON ba.belief_id = c.belief_a_id
            JOIN belief bb ON bb.belief_id = c.belief_b_id
            WHERE (ba.agent_id = %s OR bb.agent_id = %s)
              AND c.status = 'open'
            ORDER BY c.detected_at ASC
            """,
            (agent_id, agent_id),
        ).fetchall()

    return [
        Conflict(
            conflict_id=r[0],
            belief_a_id=r[1],
            belief_b_id=r[2],
            status=r[3],
            detected_at=r[4],
            resolved_at=r[5],
            resolving_agent_id=r[6],
            rationale=r[7],
        )
        for r in rows
    ]


def get_all_unresolved_conflicts(session_id: int) -> list[Conflict]:
    """Return all open conflicts whose beliefs were created in a session.
    Used by the LangGraph conflict router to collect all pending work."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.conflict_id, c.belief_a_id, c.belief_b_id,
                   c.status, c.detected_at, c.resolved_at,
                   c.resolving_agent_id, c.rationale
            FROM conflict c
            JOIN belief ba ON ba.belief_id = c.belief_a_id
            WHERE ba.session_id = %s
              AND c.status = 'open'
            ORDER BY c.detected_at ASC
            """,
            (session_id,),
        ).fetchall()

    return [
        Conflict(
            conflict_id=r[0], belief_a_id=r[1], belief_b_id=r[2],
            status=r[3], detected_at=r[4], resolved_at=r[5],
            resolving_agent_id=r[6], rationale=r[7],
        )
        for r in rows
    ]


def resolve_conflict(
    conflict_id: int,
    winning_belief_id: int,
    resolving_agent_id: int,
    rationale: str,
) -> None:
    """Call the MAMS resolve_conflict stored procedure.
    Supersedes the losing belief, logs a decision, stamps the
    conflict resolved."""
    with get_conn() as conn:
        conn.execute(
            "CALL resolve_conflict(%s, %s, %s, %s)",
            (conflict_id, winning_belief_id, resolving_agent_id, rationale),
        )
```

### `tests/phase1/test_conflict_ops.py`

```python
import pytest
from story_engine.mams import belief_ops, conflict_ops, session_ops
from story_engine.mams.connection import get_conn
from story_engine.mams.exceptions import MAMSSessionLockedError
from tests.conftest import (
    GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID,
    GREYWATCH_NPC_AGENT_IDS, GREYWATCH_CHARACTER_IDS,
    GREYWATCH_SEEDED_CONFLICT_ID,
)


@pytest.fixture
def session_with_conflict(db_pool):
    """Creates a session, inserts two competing beliefs that trigger
    a conflict, yields (session, belief_a_id, belief_b_id)."""
    s = session_ops.start_session(
        GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID, "conflict test"
    )
    char_id = GREYWATCH_CHARACTER_IDS[0]
    bid_a = belief_ops.write_belief(
        GREYWATCH_NPC_AGENT_IDS[0], "character", char_id,
        "Alive and in the keep.", 0.9, s.session_id,
    )
    bid_b = belief_ops.write_belief(
        GREYWATCH_NPC_AGENT_IDS[1], "character", char_id,
        "Dead — I saw the body.", 0.9, s.session_id,
    )
    yield s, bid_a, bid_b
    try:
        session_ops.close_session(s.session_id)
    except MAMSSessionLockedError:
        pass


def test_get_conflict_count(session_with_conflict):
    s, bid_a, _ = session_with_conflict
    count = conflict_ops.get_conflict_count(GREYWATCH_NPC_AGENT_IDS[0])
    assert count >= 1


def test_get_unresolved_conflicts_returns_conflict(session_with_conflict):
    s, bid_a, bid_b = session_with_conflict
    conflicts = conflict_ops.get_unresolved_conflicts(GREYWATCH_NPC_AGENT_IDS[0])
    assert len(conflicts) >= 1
    conflict_belief_ids = {
        (c.belief_a_id, c.belief_b_id) for c in conflicts
    }
    assert any(
        bid_a in (a, b) or bid_b in (a, b)
        for a, b in conflict_belief_ids
    )


def test_resolve_conflict_stamps_resolved(session_with_conflict):
    s, bid_a, bid_b = session_with_conflict
    conflicts = conflict_ops.get_unresolved_conflicts(GREYWATCH_NPC_AGENT_IDS[0])
    c = conflicts[0]

    conflict_ops.resolve_conflict(
        conflict_id=c.conflict_id,
        winning_belief_id=bid_a,
        resolving_agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        rationale="Director ruled: belief A is consistent with objective record.",
    )

    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, resolved_at FROM conflict WHERE conflict_id = %s",
            (c.conflict_id,),
        ).fetchone()

    assert row[0] == "resolved"
    assert row[1] is not None


def test_resolve_conflict_supersedes_losing_belief(session_with_conflict):
    s, bid_a, bid_b = session_with_conflict
    conflicts = conflict_ops.get_unresolved_conflicts(GREYWATCH_NPC_AGENT_IDS[0])
    c = conflicts[0]

    conflict_ops.resolve_conflict(
        conflict_id=c.conflict_id,
        winning_belief_id=bid_a,
        resolving_agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        rationale="A wins.",
    )

    # The losing belief (bid_b) should now have superseded_by set
    with get_conn() as conn:
        row = conn.execute(
            "SELECT superseded_by FROM belief WHERE belief_id = %s",
            (bid_b,),
        ).fetchone()

    assert row[0] is not None, "Losing belief was not superseded"


def test_resolve_conflict_logs_decision(session_with_conflict):
    s, bid_a, bid_b = session_with_conflict
    conflicts = conflict_ops.get_unresolved_conflicts(GREYWATCH_NPC_AGENT_IDS[0])
    c = conflicts[0]

    conflict_ops.resolve_conflict(
        conflict_id=c.conflict_id,
        winning_belief_id=bid_a,
        resolving_agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        rationale="Test rationale.",
    )

    with get_conn() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) FROM decision
            WHERE session_id = %s AND agent_id = %s
            """,
            (s.session_id, GREYWATCH_DIRECTOR_AGENT_ID),
        ).fetchone()[0]

    assert count >= 1
```

---

## Step 1.7 — `queries.py`

**Goal:** One Python function per query in `08_queries.sql`. Read that
file to determine the exact 10 queries and implement each one. The
function signatures below are a template — adjust column names and
return types to match the actual query output.

### `story_engine/mams/queries.py`

```python
"""
Read-only queries. One function per query in 08_queries.sql.
These are the primary way LangGraph nodes read world state.
"""
from __future__ import annotations
from datetime import datetime

from .connection import get_conn
from .models import (
    WorldState, CharacterInfo, TimelineEntry, Decision,
    Belief, LocationOccupant,
)


def get_world_state(world_id: int) -> WorldState:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT world_id, name, description FROM world WHERE world_id = %s",
            (world_id,),
        ).fetchone()
    if row is None:
        from .exceptions import MAMSNotFoundError
        raise MAMSNotFoundError("world", world_id)
    return WorldState(world_id=row[0], name=row[1], description=row[2])


def get_location_occupants(
    location_id: int,
    at_time: datetime | None = None,
) -> list[LocationOccupant]:
    """Call MAMS get_location_occupants function."""
    at_time = at_time or datetime.utcnow()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM get_location_occupants(%s, %s)",
            (location_id, at_time),
        ).fetchall()
    return [
        LocationOccupant(character_id=r[0], name=r[1], arrived_at=r[2])
        for r in rows
    ]


def get_character_timeline(character_id: int) -> list[TimelineEntry]:
    """Events involving a character, ordered chronologically."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT e.event_id, e.description, e.location_id, e.occurred_at
            FROM event e
            JOIN character_location cl
                ON cl.location_id = e.location_id
            JOIN character c
                ON c.character_id = cl.character_id
            WHERE c.character_id = %s
            ORDER BY e.occurred_at ASC
            """,
            (character_id,),
        ).fetchall()
    return [
        TimelineEntry(
            event_id=r[0], description=r[1],
            location_id=r[2], occurred_at=r[3],
        )
        for r in rows
    ]


def get_session_decisions(session_id: int) -> list[Decision]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT decision_id, session_id, agent_id,
                   decision_type, rationale, created_at
            FROM decision
            WHERE session_id = %s
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
    return [
        Decision(
            decision_id=r[0], session_id=r[1], agent_id=r[2],
            decision_type=r[3], rationale=r[4], created_at=r[5],
        )
        for r in rows
    ]


def get_recent_memories(agent_id: int, limit: int = 20) -> list[str]:
    """Return content strings from recent memory rows for an agent."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT content FROM memory
            WHERE agent_id = %s
            ORDER BY last_accessed_at DESC
            LIMIT %s
            """,
            (agent_id, limit),
        ).fetchall()
    return [r[0] for r in rows]


def get_active_characters(world_id: int) -> list[CharacterInfo]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.character_id, c.name,
                   cl.location_id, c.is_active
            FROM character c
            LEFT JOIN character_location cl
                ON cl.character_id = c.character_id
                AND cl.departed_at IS NULL
            WHERE c.world_id = %s AND c.is_active = TRUE
            ORDER BY c.character_id
            """,
            (world_id,),
        ).fetchall()
    return [
        CharacterInfo(
            character_id=r[0], name=r[1],
            location_id=r[2], is_active=r[3],
        )
        for r in rows
    ]


# Implement remaining functions to cover all 10 queries in 08_queries.sql.
# Each function follows the same pattern: parameterized query → dataclass list.
```

### `tests/phase1/test_queries.py`

```python
"""One test per query function. All assertions are against known
Greywatch seed data. Fill expected values from 04_seed_data.sql."""
import pytest
from story_engine.mams import queries
from tests.conftest import (
    GREYWATCH_WORLD_ID, GREYWATCH_CHARACTER_IDS, GREYWATCH_LOCATION_IDS,
    GREYWATCH_DIRECTOR_AGENT_ID,
)


def test_get_world_state(db_pool):
    ws = queries.get_world_state(GREYWATCH_WORLD_ID)
    assert ws.world_id == GREYWATCH_WORLD_ID
    assert ws.name  # Greywatch world has a name


def test_get_active_characters(db_pool):
    chars = queries.get_active_characters(GREYWATCH_WORLD_ID)
    assert len(chars) == 7  # Greywatch has 7 characters


def test_get_location_occupants(db_pool):
    occupants = queries.get_location_occupants(GREYWATCH_LOCATION_IDS[0])
    assert isinstance(occupants, list)  # may be empty depending on location


def test_get_recent_memories_returns_list(db_pool):
    memories = queries.get_recent_memories(GREYWATCH_DIRECTOR_AGENT_ID)
    assert isinstance(memories, list)
```

---

## Step 1.8 — `__init__.py` population

Populate `story_engine/mams/__init__.py` with the full public API as
listed in Step 1.0. Run the full Phase 1 test suite:

```bash
pytest tests/phase1/ -v --tb=short
```

All tests must pass before starting Phase 2.

---

# PHASE 2 — LangGraph Orchestration Layer

Build steps 2.0 → 2.10 in order. Do not begin until Phase 1 is fully
green. Run `pytest tests/phase2/` after each step.

---

## Step 2.0 — LangGraph setup

```bash
pip install langgraph langchain-anthropic
```

Confirm in `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
STORY_ENGINE_MODEL=claude-sonnet-4-20250514
STORY_ENGINE_MAX_TURNS=10
```

Create `story_engine/graph/__init__.py` (empty for now).

---

## Step 2.1 — State schema (`state.py`)

**Goal:** The canonical LangGraph state object. This is the ephemeral
working memory for one run. It does NOT duplicate durable facts — those
live in MAMS.

### `story_engine/graph/state.py`

```python
from __future__ import annotations
from typing import TypedDict


class StoryEngineState(TypedDict):
    # ── Session identity ──────────────────────────────────────────────
    session_id: int              # MAMS session_id for this run
    world_id: int
    director_agent_id: int

    # ── Run control ───────────────────────────────────────────────────
    current_turn: int            # incremented by director_plan
    max_turns: int               # from env STORY_ENGINE_MAX_TURNS
    run_complete: bool           # set True by director_plan when done

    # ── Agent roster (hydrated at session start) ──────────────────────
    active_agent_ids: list[int]  # all agents enrolled in this session

    # ── Within-turn routing signals ───────────────────────────────────
    # Set by director_plan; consumed by conditional edges.
    invoke_writer: bool
    invoke_lore_keeper: bool
    invoke_npc_ids: list[int]    # character_ids of NPCs to invoke

    # ── Event queue ───────────────────────────────────────────────────
    # event_ids created this turn, awaiting propagation
    pending_event_ids: list[int]

    # turn_events: raw event dicts from director_plan LLM output,
    # before they are written to MAMS
    turn_events: list[dict]      # {description, location_id, event_type_id}

    # ── Conflict queue ────────────────────────────────────────────────
    # conflict_ids detected this turn, awaiting resolution
    pending_conflict_ids: list[int]

    # ── Narrative output ──────────────────────────────────────────────
    # Accumulated prose passages from writer_node. Ephemeral — written
    # to MAMS memory rows at session close.
    narrative_output: list[str]

    # ── Session summary ───────────────────────────────────────────────
    # Populated by director_plan on final turn
    session_summary: str


def initial_state(
    world_id: int,
    director_agent_id: int,
    max_turns: int = 10,
) -> StoryEngineState:
    """Return a default-initialised state. session_id is set to 0
    until director_init_node calls start_session()."""
    return StoryEngineState(
        session_id=0,
        world_id=world_id,
        director_agent_id=director_agent_id,
        current_turn=0,
        max_turns=max_turns,
        run_complete=False,
        active_agent_ids=[],
        invoke_writer=False,
        invoke_lore_keeper=False,
        invoke_npc_ids=[],
        pending_event_ids=[],
        turn_events=[],
        pending_conflict_ids=[],
        narrative_output=[],
        session_summary="",
    )
```

---

## Step 2.2 — Session lifecycle nodes (`nodes/director.py`, part 1)

**Goal:** `director_init_node` and `director_close_node`. These bracket
every run. Prove the database round-trip before building anything else.

### `story_engine/graph/nodes/director.py` (partial — init and close only)

```python
from __future__ import annotations
import os

from story_engine.mams import session_ops, queries
from story_engine.graph.state import StoryEngineState


def director_init_node(state: StoryEngineState) -> dict:
    """Open a MAMS session and hydrate run-state.
    Called once at the start of every run."""
    session = session_ops.start_session(
        world_id=state["world_id"],
        director_agent_id=state["director_agent_id"],
        narrative_context=f"story-engine run, world {state['world_id']}",
    )
    agents = session_ops.get_active_agents(session.session_id)

    return {
        "session_id": session.session_id,
        "active_agent_ids": [a.agent_id for a in agents],
        "max_turns": int(os.environ.get("STORY_ENGINE_MAX_TURNS", 10)),
    }


def director_close_node(state: StoryEngineState) -> dict:
    """Close the MAMS session. Called once at the end of every run."""
    session_ops.close_session(state["session_id"])
    return {}
```

### `tests/phase2/test_graph_roundtrip.py`

```python
"""Minimal round-trip: init → close. Proves DB integration before
any LLM calls are made."""
import pytest
from langgraph.graph import StateGraph, START, END

from story_engine.mams.connection import init_pool
from story_engine.mams import session_ops
from story_engine.graph.state import StoryEngineState, initial_state
from story_engine.graph.nodes.director import (
    director_init_node, director_close_node,
)
from tests.conftest import GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID


@pytest.fixture(scope="module")
def minimal_graph():
    builder = StateGraph(StoryEngineState)
    builder.add_node("init", director_init_node)
    builder.add_node("close", director_close_node)
    builder.add_edge(START, "init")
    builder.add_edge("init", "close")
    builder.add_edge("close", END)
    return builder.compile()


def test_round_trip(db_pool, minimal_graph):
    state = initial_state(
        world_id=GREYWATCH_WORLD_ID,
        director_agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
    )
    result = minimal_graph.invoke(state)

    assert result["session_id"] > 0

    # Verify MAMS shows the session as completed
    s = session_ops.get_session(result["session_id"])
    assert s.status == "completed"
    assert s.ended_at is not None
```

---

## Step 2.3 — Prompts

All prompt templates live in `story_engine/graph/prompts/`. They are
plain strings — no LangChain prompt objects, so they are easy to read,
edit, and test independently.

### `story_engine/graph/prompts/director.py`

```python
DIRECTOR_PLAN = """\
You are the Director of an ongoing narrative. Your role is to decide what
events occur in the story world this turn.

WORLD: {world_name}
{world_description}

RECENT MEMORY:
{recent_memories}

ACTIVE CHARACTERS:
{character_list}

CURRENT TURN: {current_turn} of {max_turns}
OPEN CONFLICTS: {conflict_count}

Decide what happens this turn. Respond ONLY with a valid JSON object —
no preamble, no markdown fences, no commentary:

{{
  "events": [
    {{
      "description": "<what happened>",
      "location_id": <int>,
      "event_type_id": <int>
    }}
  ],
  "invoke_writer": <true|false>,
  "invoke_lore_keeper": <true|false>,
  "invoke_npc_ids": [<character_id>, ...],
  "end_session": <true|false>,
  "session_summary": "<string — only include if end_session is true>"
}}
"""

DIRECTOR_PLAN_FINAL_TURN = """\
This is the final turn ({current_turn} of {max_turns}). You must set
end_session to true and provide a session_summary.
""" + DIRECTOR_PLAN
```

### `story_engine/graph/prompts/writer.py`

```python
WRITER_NARRATE = """\
You are the Narrator of an ongoing story. Write the next passage of
narrative prose based on what just happened.

EVENTS THIS TURN:
{events_this_turn}

ACTIVE CHARACTERS AND LOCATIONS:
{character_states}

PREVIOUS PASSAGE (for continuity):
{last_narrative}

Write 2–4 paragraphs of literary narrative prose. Do not include JSON,
headers, or any metadata. Only the story text.
"""
```

### `story_engine/graph/prompts/lore_keeper.py`

```python
LORE_KEEPER_CHECK = """\
You are the Lore-keeper. Your role is to verify story facts and record
confirmed world-state beliefs.

PROPOSED EVENTS THIS TURN:
{proposed_events}

EXISTING WORLD BELIEFS (from MAMS):
{existing_beliefs}

For each proposed event, determine if it is consistent with existing lore.
Respond ONLY with a valid JSON object — no preamble or markdown fences:

{{
  "beliefs": [
    {{
      "subject_type": "<character|event|location|world_state>",
      "subject_id": <int>,
      "content": "<what you believe is now true>",
      "confidence": <float 0.0–1.0>,
      "consistent": <true|false>
    }}
  ],
  "lore_violations": ["<description of violation, or empty list if none>"]
}}
"""
```

### `story_engine/graph/prompts/npc.py`

```python
NPC_REACT = """\
You are portraying {character_name} in an ongoing story.

YOUR CHARACTER: {character_description}

WHAT YOU WITNESSED THIS TURN:
{witnessed_events}

WHAT YOU CURRENTLY BELIEVE (from MAMS):
{current_beliefs}

Based on what you witnessed, form your updated beliefs. Respond ONLY with
a valid JSON object — no preamble or markdown fences:

{{
  "beliefs": [
    {{
      "subject_type": "<character|event|location|world_state|relationship>",
      "subject_id": <int>,
      "content": "<what your character now believes>",
      "confidence": <float 0.0–1.0>
    }}
  ],
  "character_state": "<brief description of your character's current state>"
}}
"""
```

### `story_engine/graph/prompts/conflict.py`

```python
CONFLICT_RESOLVE = """\
You are the Director resolving a factual conflict between two agents' beliefs.

BELIEF A (Agent {agent_a_id}):
  Subject: {subject_type} id={subject_id}
  Content: {belief_a_content}
  Confidence: {belief_a_confidence}

BELIEF B (Agent {agent_b_id}):
  Subject: {subject_type} id={subject_id}
  Content: {belief_b_content}
  Confidence: {belief_b_confidence}

OBJECTIVE RECORD (from MAMS):
{objective_facts}

Determine which belief is more accurate. Respond ONLY with a valid JSON
object — no preamble or markdown fences:

{{
  "winning_belief_id": <belief_id>,
  "rationale": "<one-sentence explanation>"
}}
"""
```

---

## Step 2.4 — LLM helper (`nodes/_llm.py`)

A shared function for making Anthropic API calls. All nodes use this
so the model name is configured in one place.

### `story_engine/graph/nodes/_llm.py`

```python
from __future__ import annotations
import json
import os
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage


_model: ChatAnthropic | None = None


def get_model() -> ChatAnthropic:
    global _model
    if _model is None:
        _model = ChatAnthropic(
            model=os.environ.get(
                "STORY_ENGINE_MODEL", "claude-sonnet-4-20250514"
            ),
            temperature=0.7,
        )
    return _model


def call_llm(prompt: str) -> str:
    """Make a single-turn call to the model. Returns the raw text response."""
    response = get_model().invoke([HumanMessage(content=prompt)])
    return response.content


def call_llm_json(prompt: str) -> dict:
    """Call the model and parse the response as JSON.
    Strips markdown code fences if present.
    Raises ValueError if the response is not valid JSON."""
    raw = call_llm(prompt)
    # Strip ```json ... ``` or ``` ... ``` fences if the model adds them
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model returned non-JSON response:\n{raw}\n\nError: {e}"
        ) from e
```

---

## Step 2.5 — `director_plan_node` (`nodes/director.py`, full)

**Goal:** The Director decides what happens this turn. Calls the LLM,
writes events, sets routing signals in state.

```python
# Add to story_engine/graph/nodes/director.py

from story_engine.graph.nodes._llm import call_llm_json
from story_engine.graph.prompts import director as director_prompts
from story_engine.mams import queries, conflict_ops


def director_plan_node(state: StoryEngineState) -> dict:
    """Director LLM call — decides events and which agents to invoke."""
    world = queries.get_world_state(state["world_id"])
    characters = queries.get_active_characters(state["world_id"])
    memories = queries.get_recent_memories(state["director_agent_id"])
    conflict_count = conflict_ops.get_conflict_count(state["director_agent_id"])

    is_final = (state["current_turn"] + 1) >= state["max_turns"]
    template = (
        director_prompts.DIRECTOR_PLAN_FINAL_TURN
        if is_final
        else director_prompts.DIRECTOR_PLAN
    )

    prompt = template.format(
        world_name=world.name,
        world_description=world.description or "",
        recent_memories="\n".join(memories) if memories else "None yet.",
        character_list="\n".join(
            f"  - {c.name} (id={c.character_id}, location={c.location_id})"
            for c in characters
        ),
        current_turn=state["current_turn"] + 1,
        max_turns=state["max_turns"],
        conflict_count=conflict_count,
    )

    result = call_llm_json(prompt)

    return {
        "current_turn": state["current_turn"] + 1,
        "turn_events": result.get("events", []),
        "invoke_writer": result.get("invoke_writer", True),
        "invoke_lore_keeper": result.get("invoke_lore_keeper", False),
        "invoke_npc_ids": result.get("invoke_npc_ids", []),
        "run_complete": result.get("end_session", False),
        "session_summary": result.get("session_summary", ""),
    }
```

---

## Step 2.6 — `event_node` (`nodes/events.py`)

**Goal:** Materialise this turn's events into MAMS and propagate them.

### `story_engine/graph/nodes/events.py`

```python
from __future__ import annotations

from story_engine.mams import event_ops
from story_engine.graph.state import StoryEngineState


def event_node(state: StoryEngineState) -> dict:
    """Write each event from turn_events to MAMS and propagate."""
    new_event_ids = []
    for ev in state["turn_events"]:
        event_id = event_ops.create_event(
            world_id=state["world_id"],
            event_type_id=ev["event_type_id"],
            location_id=ev["location_id"],
            description=ev["description"],
        )
        event_ops.propagate_event(event_id)
        new_event_ids.append(event_id)

    return {
        "pending_event_ids": state["pending_event_ids"] + new_event_ids,
        "turn_events": [],  # consumed
    }
```

---

## Step 2.7 — `writer_node` (`nodes/writer.py`)

### `story_engine/graph/nodes/writer.py`

```python
from __future__ import annotations

from story_engine.graph.nodes._llm import call_llm
from story_engine.graph.prompts import writer as writer_prompts
from story_engine.mams import queries
from story_engine.graph.state import StoryEngineState


def writer_node(state: StoryEngineState) -> dict:
    """Generate a prose passage for this turn's events."""
    if not state["invoke_writer"]:
        return {}

    characters = queries.get_active_characters(state["world_id"])
    last_narrative = (
        state["narrative_output"][-1]
        if state["narrative_output"]
        else "The story begins."
    )

    events_text = "\n".join(
        f"  - {ev['description']}" for ev in state.get("turn_events", [])
    ) or "  (no new events this turn)"

    character_states = "\n".join(
        f"  - {c.name}: location_id={c.location_id}"
        for c in characters
    )

    prompt = writer_prompts.WRITER_NARRATE.format(
        events_this_turn=events_text,
        character_states=character_states,
        last_narrative=last_narrative,
    )

    passage = call_llm(prompt)
    return {"narrative_output": state["narrative_output"] + [passage]}
```

---

## Step 2.8 — `lore_keeper_node` (`nodes/lore_keeper.py`)

### `story_engine/graph/nodes/lore_keeper.py`

```python
from __future__ import annotations

from story_engine.graph.nodes._llm import call_llm_json
from story_engine.graph.prompts import lore_keeper as lk_prompts
from story_engine.mams import belief_ops, queries
from story_engine.graph.state import StoryEngineState


def lore_keeper_node(state: StoryEngineState) -> dict:
    """Verify lore consistency and write confirmed beliefs."""
    if not state["invoke_lore_keeper"]:
        return {}

    # Gather existing beliefs about the world from MAMS
    # (use a representative sample — e.g. world_state beliefs)
    # This is a simplified gather; expand as needed.
    existing_beliefs_text = "(query MAMS for relevant existing beliefs here)"

    events_text = "\n".join(
        f"  - {ev['description']}" for ev in state.get("turn_events", [])
    ) or "  (none)"

    prompt = lk_prompts.LORE_KEEPER_CHECK.format(
        proposed_events=events_text,
        existing_beliefs=existing_beliefs_text,
    )

    result = call_llm_json(prompt)

    # Write each belief to MAMS — trigger handles conflict detection
    lore_keeper_agent_id = _get_lore_keeper_id(state["active_agent_ids"])
    if lore_keeper_agent_id:
        for b in result.get("beliefs", []):
            belief_ops.write_belief(
                agent_id=lore_keeper_agent_id,
                subject_type=b["subject_type"],
                subject_id=b["subject_id"],
                content=b["content"],
                confidence=b["confidence"],
                session_id=state["session_id"],
            )

    return {}


def _get_lore_keeper_id(active_agent_ids: list[int]) -> int | None:
    """Look up the lore_keeper agent from the active roster.
    Returns None if no lore_keeper is enrolled."""
    from story_engine.mams.connection import get_conn
    if not active_agent_ids:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT a.agent_id FROM agent a
            JOIN agent_type at ON at.agent_type_id = a.agent_type_id
            WHERE a.agent_id = ANY(%s)
              AND at.name = 'lore_keeper'
            LIMIT 1
            """,
            (active_agent_ids,),
        ).fetchone()
    return row[0] if row else None
```

---

## Step 2.9 — `npc_node` (`nodes/npc.py`)

### `story_engine/graph/nodes/npc.py`

```python
from __future__ import annotations

from story_engine.graph.nodes._llm import call_llm_json
from story_engine.graph.prompts import npc as npc_prompts
from story_engine.mams import belief_ops, queries
from story_engine.mams.connection import get_conn
from story_engine.graph.state import StoryEngineState


def npc_node(state: StoryEngineState) -> dict:
    """Each invoked NPC character forms beliefs based on what it witnessed."""
    if not state["invoke_npc_ids"]:
        return {}

    for character_id in state["invoke_npc_ids"]:
        agent_id = _get_agent_for_character(character_id)
        if agent_id is None:
            continue  # no agent portrays this character

        character = _get_character(character_id)
        timeline = queries.get_character_timeline(character_id)
        current_beliefs = belief_ops.get_agent_belief(
            agent_id, "character", character_id
        )

        witnessed = "\n".join(
            f"  - {e.description}" for e in timeline[-5:]  # last 5 events
        ) or "  (nothing witnessed recently)"

        beliefs_text = "\n".join(
            f"  - [{b.confidence:.0%}] {b.content}"
            for b in current_beliefs
        ) or "  (no existing beliefs)"

        prompt = npc_prompts.NPC_REACT.format(
            character_name=character["name"],
            character_description=character.get("description", ""),
            witnessed_events=witnessed,
            current_beliefs=beliefs_text,
        )

        result = call_llm_json(prompt)

        for b in result.get("beliefs", []):
            belief_ops.write_belief(
                agent_id=agent_id,
                subject_type=b["subject_type"],
                subject_id=b["subject_id"],
                content=b["content"],
                confidence=b["confidence"],
                session_id=state["session_id"],
            )

    return {}


def _get_agent_for_character(character_id: int) -> int | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT agent_id FROM agent_character WHERE character_id = %s LIMIT 1",
            (character_id,),
        ).fetchone()
    return row[0] if row else None


def _get_character(character_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT character_id, name, description FROM character WHERE character_id = %s",
            (character_id,),
        ).fetchone()
    if row is None:
        return {"name": f"Character {character_id}", "description": ""}
    return {"character_id": row[0], "name": row[1], "description": row[2]}
```

---

## Step 2.10 — Conflict router + resolution node (`nodes/conflict.py`)

### `story_engine/graph/nodes/conflict.py`

```python
from __future__ import annotations

from story_engine.graph.nodes._llm import call_llm_json
from story_engine.graph.prompts import conflict as conflict_prompts
from story_engine.mams import belief_ops, conflict_ops, queries
from story_engine.mams.connection import get_conn
from story_engine.graph.state import StoryEngineState


def belief_flush_node(state: StoryEngineState) -> dict:
    """After all agents have acted, collect any new conflicts from MAMS
    and add them to pending_conflict_ids."""
    new_conflicts = conflict_ops.get_all_unresolved_conflicts(state["session_id"])
    new_ids = [
        c.conflict_id for c in new_conflicts
        if c.conflict_id not in state["pending_conflict_ids"]
    ]
    return {
        "pending_conflict_ids": state["pending_conflict_ids"] + new_ids
    }


def conflict_route(state: StoryEngineState) -> str:
    """Conditional edge function. Returns the name of the next node.

    Routing logic:
      - pending conflicts → 'resolve_conflict'
      - no conflicts + run complete → 'extract_memory'
      - no conflicts + not complete → 'director_plan'
    """
    if state["pending_conflict_ids"]:
        return "resolve_conflict"
    if state["run_complete"]:
        return "extract_memory"
    return "director_plan"


def conflict_resolve_node(state: StoryEngineState) -> dict:
    """Resolve the first pending conflict. The Director LLM picks the
    winning belief; MAMS records the resolution."""
    if not state["pending_conflict_ids"]:
        return {}

    conflict_id = state["pending_conflict_ids"][0]
    remaining = state["pending_conflict_ids"][1:]

    # Fetch the conflict and both beliefs
    with get_conn() as conn:
        row = conn.execute(
            "SELECT belief_a_id, belief_b_id FROM conflict WHERE conflict_id = %s",
            (conflict_id,),
        ).fetchone()

    if row is None:
        return {"pending_conflict_ids": remaining}

    belief_a_id, belief_b_id = row
    belief_a = _get_belief(belief_a_id)
    belief_b = _get_belief(belief_b_id)

    if belief_a is None or belief_b is None:
        return {"pending_conflict_ids": remaining}

    # Gather objective facts about the subject for context
    objective_facts = _get_objective_facts(
        belief_a["subject_type"], belief_a["subject_id"]
    )

    prompt = conflict_prompts.CONFLICT_RESOLVE.format(
        agent_a_id=belief_a["agent_id"],
        agent_b_id=belief_b["agent_id"],
        subject_type=belief_a["subject_type"],
        subject_id=belief_a["subject_id"],
        belief_a_content=belief_a["content"],
        belief_a_confidence=belief_a["confidence"],
        belief_b_content=belief_b["content"],
        belief_b_confidence=belief_b["confidence"],
        objective_facts=objective_facts,
    )

    result = call_llm_json(prompt)
    winning_id = result["winning_belief_id"]
    rationale = result.get("rationale", "Director resolved conflict.")

    conflict_ops.resolve_conflict(
        conflict_id=conflict_id,
        winning_belief_id=winning_id,
        resolving_agent_id=state["director_agent_id"],
        rationale=rationale,
    )

    return {"pending_conflict_ids": remaining}


def _get_belief(belief_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT belief_id, agent_id, subject_type, subject_id,
                   content, confidence
            FROM belief WHERE belief_id = %s
            """,
            (belief_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "belief_id": row[0], "agent_id": row[1],
        "subject_type": row[2], "subject_id": row[3],
        "content": row[4], "confidence": float(row[5]),
    }


def _get_objective_facts(subject_type: str, subject_id: int) -> str:
    """Return a plain-text summary of objective facts about the subject
    from the MAMS objective layer. Used to inform conflict resolution."""
    with get_conn() as conn:
        if subject_type == "character":
            row = conn.execute(
                "SELECT name, description FROM character WHERE character_id = %s",
                (subject_id,),
            ).fetchone()
            if row:
                return f"Character '{row[0]}': {row[1]}"
        elif subject_type == "event":
            row = conn.execute(
                "SELECT description, occurred_at FROM event WHERE event_id = %s",
                (subject_id,),
            ).fetchone()
            if row:
                return f"Event: {row[0]} (at {row[1]})"
    return "(no objective record found)"
```

---

## Step 2.11 — Memory extraction node (`nodes/director.py`, full close)

```python
# Add to story_engine/graph/nodes/director.py

from story_engine.mams.connection import get_conn


def memory_extraction_node(state: StoryEngineState) -> dict:
    """Write the session's narrative output to MAMS memory rows.
    These survive the run and seed future sessions."""
    if not state["narrative_output"]:
        return {}

    # Write each passage as a memory row for the Director agent
    with get_conn() as conn:
        for passage in state["narrative_output"]:
            conn.execute(
                """
                INSERT INTO memory
                    (agent_id, session_id, content)
                VALUES (%s, %s, %s)
                """,
                (
                    state["director_agent_id"],
                    state["session_id"],
                    passage[:2000],  # respect any column length limit
                ),
            )

    # Write the session summary as a memory row if present
    if state["session_summary"]:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO memory
                    (agent_id, session_id, content)
                VALUES (%s, %s, %s)
                """,
                (
                    state["director_agent_id"],
                    state["session_id"],
                    f"[SUMMARY] {state['session_summary']}",
                ),
            )

    return {}
```

---

## Step 2.12 — Full graph wiring (`graph/graph.py`)

**Goal:** Wire all nodes and edges into the complete `StateGraph`.

### `story_engine/graph/graph.py`

```python
from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from story_engine.graph.state import StoryEngineState
from story_engine.graph.nodes.director import (
    director_init_node,
    director_plan_node,
    director_close_node,
    memory_extraction_node,
)
from story_engine.graph.nodes.events import event_node
from story_engine.graph.nodes.writer import writer_node
from story_engine.graph.nodes.lore_keeper import lore_keeper_node
from story_engine.graph.nodes.npc import npc_node
from story_engine.graph.nodes.conflict import (
    belief_flush_node,
    conflict_route,
    conflict_resolve_node,
)


def build_graph() -> StateGraph:
    builder = StateGraph(StoryEngineState)

    # ── Nodes ──────────────────────────────────────────────────────────
    builder.add_node("director_init",    director_init_node)
    builder.add_node("director_plan",    director_plan_node)
    builder.add_node("event",            event_node)
    builder.add_node("writer",           writer_node)
    builder.add_node("lore_keeper",      lore_keeper_node)
    builder.add_node("npc",              npc_node)
    builder.add_node("belief_flush",     belief_flush_node)
    builder.add_node("resolve_conflict", conflict_resolve_node)
    builder.add_node("extract_memory",   memory_extraction_node)
    builder.add_node("director_close",   director_close_node)

    # ── Entry ──────────────────────────────────────────────────────────
    builder.add_edge(START, "director_init")
    builder.add_edge("director_init", "director_plan")

    # ── Turn loop ──────────────────────────────────────────────────────
    # director_plan sets turn_events and routing signals in state
    builder.add_edge("director_plan", "event")

    # After events are created, run writer, lore_keeper, npcs in sequence.
    # (Parallel execution via Send API can be added later if needed.)
    builder.add_edge("event",       "writer")
    builder.add_edge("writer",      "lore_keeper")
    builder.add_edge("lore_keeper", "npc")
    builder.add_edge("npc",         "belief_flush")

    # ── Conflict router: the main branching point ─────────────────────
    builder.add_conditional_edges(
        "belief_flush",
        conflict_route,
        {
            "resolve_conflict": "resolve_conflict",
            "director_plan":    "director_plan",
            "extract_memory":   "extract_memory",
        },
    )

    # Conflict resolution loops back to the router until queue is empty
    builder.add_edge("resolve_conflict", "belief_flush")

    # ── Close ──────────────────────────────────────────────────────────
    builder.add_edge("extract_memory",  "director_close")
    builder.add_edge("director_close",  END)

    return builder.compile()


# Convenience: pre-built graph instance
graph = build_graph()
```

### Graph flow diagram

```
START
  └── director_init          (open MAMS session, hydrate state)
        └── director_plan    (LLM: decide events + routing)
              └── event       (write + propagate events to MAMS)
                    └── writer        (LLM: narrative prose)
                          └── lore_keeper   (LLM: verify lore, write beliefs)
                                └── npc           (LLM: NPC reactions, write beliefs)
                                      └── belief_flush  (collect new conflicts)
                                            │
                          ┌───────────────────┤
                          │                   │                    │
                   [conflicts]           [done, no conflicts]  [continue, no conflicts]
                          │                   │                    │
                  resolve_conflict      extract_memory        director_plan
                          │                   │                 (loop)
                    (loop back to        director_close
                    belief_flush)              │
                                             END
```

---

## Step 2.13 — Integration test (`tests/phase2/test_full_session.py`)

```python
"""Full session integration test. Makes real LLM calls against
Greywatch seed data. Requires ANTHROPIC_API_KEY in environment.
Mark slow tests with pytest.mark.slow and skip in CI if needed."""
import pytest
from story_engine.mams import session_ops
from story_engine.graph.graph import graph
from story_engine.graph.state import initial_state
from tests.conftest import GREYWATCH_WORLD_ID, GREYWATCH_DIRECTOR_AGENT_ID


@pytest.mark.slow
def test_full_session_completes(db_pool):
    """Run the full graph with max_turns=2. Verify a MAMS session
    opens, runs, and closes cleanly."""
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    state = initial_state(
        world_id=GREYWATCH_WORLD_ID,
        director_agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        max_turns=2,
    )
    result = graph.invoke(state)

    assert result["session_id"] > 0
    assert result["run_complete"] is True

    s = session_ops.get_session(result["session_id"])
    assert s.status == "completed"
    assert s.ended_at is not None
    assert len(result["narrative_output"]) >= 1


@pytest.mark.slow
def test_full_session_writes_memory(db_pool):
    """Verify that memory rows are written to MAMS at session close."""
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    from story_engine.mams.connection import get_conn

    state = initial_state(
        world_id=GREYWATCH_WORLD_ID,
        director_agent_id=GREYWATCH_DIRECTOR_AGENT_ID,
        max_turns=2,
    )
    result = graph.invoke(state)

    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM memory WHERE session_id = %s",
            (result["session_id"],),
        ).fetchone()[0]

    assert count >= 1
```

---

## Reference: MAMS SQL files

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

Rebuild from scratch:
```bash
dropdb mams && createdb mams
psql -d mams -v ON_ERROR_STOP=1 -f mams_sql/00_run_all.sql
```

---

## Scope guardrails

- MAMS database is **done**. Schema changes go in a new `09_...sql`
  migration — never edit existing scripts.
- Phase 1 must be **fully green** before Phase 2 begins.
- Memory logic stays in SQL. Orchestration logic stays in LangGraph.
  The Python layer is a bridge with zero business logic.
- `ITEM` / `ITEM_LOCATION` are deferred until inventory is genuinely
  needed.
- `call_llm_json` should be the only place JSON parsing happens.
  Nodes receive dicts, not strings.
- Every MAMS write from a node goes through the Python layer.
  No node touches psycopg directly.

---

*Specification complete. MAMS database verified on PostgreSQL 16.
Phase 1 builds first; Phase 2 follows.*
