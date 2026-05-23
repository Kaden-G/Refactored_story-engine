"""Run a single Director session — the full round-trip.

Usage:
    python run_session.py

Requires:
  - PostgreSQL running with MAMS seeded (00_run_all.sql)
  - .env with correct MAMS_DB_* vars
  - (Optional) ANTHROPIC_API_KEY in .env for LLM-backed Director

Without an API key, the Director uses a rule-based fallback so you
can prove the round-trip works end-to-end.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()

from story_engine.dal import MamsDAL, get_pool, close_pool
from story_engine.orchestration import build_director_graph, build_llm


def main() -> None:
    pool = get_pool()
    dal = MamsDAL(pool)

    # Resolve the Greywatch world and Director agent
    world = dal.get_world_by_name("Greywatch")
    if world is None:
        print("ERROR: Greywatch world not found. Is the database seeded?")
        sys.exit(1)

    director = dal.get_agent_by_name("Director Agent")
    if director is None:
        print("ERROR: Director Agent not found.")
        sys.exit(1)

    # Optionally wire up an LLM (model id from STORY_ENGINE_MODEL).
    llm = build_llm()
    if llm is not None:
        print("Using Claude as Director LLM.")
    else:
        print("No ANTHROPIC_API_KEY — using rule-based Director fallback.")

    # Build and run the graph
    graph = build_director_graph(dal, llm=llm)

    print(f"\nStarting session for world '{world.name}' (id={world.world_id})...")
    print("=" * 60)

    result = graph.invoke({
        "world_id": world.world_id,
        "director_agent_id": director.agent_id,
        "narrative_context": "Continue the Door Three search arc.",
    })

    # Print the message log
    print("\n── Session transcript ─────────────────────────────────────")
    for msg in result.get("messages", []):
        role = type(msg).__name__.replace("Message", "")
        print(f"[{role}] {msg.content}")

    print("=" * 60)
    print(f"Session ID: {result.get('session_id')}")
    print(f"Turns: {result.get('turn_number')}")
    print(f"Unresolved conflicts: {len(result.get('unresolved_conflicts', []))}")

    close_pool()


if __name__ == "__main__":
    main()
