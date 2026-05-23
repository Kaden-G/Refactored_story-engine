"""Session management and SSE streaming routes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from api.schemas import MessageOut, SessionOut, SessionStartRequest, SSEMessage
from story_engine.orchestration import build_director_graph, build_llm

router = APIRouter()
log = logging.getLogger(__name__)

# In-memory store for active sessions (single-process; fine for MVP).
# Keyed by MAMS session_id so callers can correlate back to the DB.
_active_sessions: dict[int, dict] = {}


def _dal(request: Request):
    return request.app.state.dal


@router.post("/start", response_model=SessionOut)
def start_session(body: SessionStartRequest, request: Request):
    """Open a MAMS session and prepare a Director graph for streaming.

    Returns the real MAMS session_id so the client can correlate
    streamed events back to durable records. The graph itself runs
    lazily when GET /{session_id}/stream is hit.
    """
    dal = _dal(request)

    llm = build_llm()
    graph = build_director_graph(dal, llm=llm, max_turns=body.max_turns)

    # Open the MAMS session synchronously so we can return its real id.
    session_id = dal.start_session(
        body.world_id, body.director_agent_id, body.narrative_context,
    )

    initial_state = {
        "session_id": session_id,
        "world_id": body.world_id,
        "director_agent_id": body.director_agent_id,
        "narrative_context": body.narrative_context,
    }

    _active_sessions[session_id] = {
        "graph": graph,
        "initial_state": initial_state,
        "messages": [],
        "finished": False,
    }

    return SessionOut(
        session_id=session_id,
        world_id=body.world_id,
        status="active",
        turn_number=0,
        narrative_context=body.narrative_context,
    )


@router.get("/{session_id}/stream")
async def stream_session(session_id: int, request: Request):
    """SSE endpoint: runs the full Director loop, streaming messages."""
    session_data = _active_sessions.get(session_id)
    if session_data is None:
        raise HTTPException(404, "Session not found. Call /start first.")

    if session_data["finished"]:
        raise HTTPException(400, "Session already completed.")

    async def event_generator() -> AsyncGenerator[dict, None]:
        graph = session_data["graph"]
        initial_state = session_data["initial_state"]

        try:
            # Stream the graph execution
            # LangGraph's .stream() yields partial state updates per node
            for step in graph.stream(initial_state):
                # Each step is a dict: { "node_name": partial_state_update }
                for node_name, update in step.items():
                    messages = update.get("messages", [])
                    turn = update.get("turn_number")
                    should_end = update.get("should_end", False)

                    if turn is not None:
                        yield {
                            "event": "turn_start",
                            "data": json.dumps(
                                SSEMessage(
                                    event_type="turn_start",
                                    turn_number=turn,
                                ).model_dump()
                            ),
                        }

                    for msg in messages:
                        role = type(msg).__name__.replace("Message", "")
                        content = msg.content

                        # Parse agent name from content prefix like "[Director] ..."
                        agent_name = None
                        if content.startswith("[") and "]" in content:
                            bracket_end = content.index("]")
                            agent_name = content[1:bracket_end]
                            content = content[bracket_end + 2:]

                        sse_msg = SSEMessage(
                            event_type="message",
                            turn_number=turn,
                            role=role.lower(),
                            agent_name=agent_name,
                            content=content,
                            should_end=should_end,
                        )

                        session_data["messages"].append(sse_msg)

                        yield {
                            "event": "message",
                            "data": json.dumps(sse_msg.model_dump()),
                        }

                    if should_end:
                        yield {
                            "event": "session_end",
                            "data": json.dumps(
                                SSEMessage(
                                    event_type="session_end",
                                    content="Session completed.",
                                    should_end=True,
                                ).model_dump()
                            ),
                        }

                # Yield control to the event loop between steps
                await asyncio.sleep(0)

        except Exception as e:
            log.exception("Error during session streaming")
            yield {
                "event": "error",
                "data": json.dumps(
                    SSEMessage(
                        event_type="error",
                        content=str(e),
                    ).model_dump()
                ),
            }
        finally:
            session_data["finished"] = True

    return EventSourceResponse(event_generator())


@router.get("/{session_id}/messages", response_model=list[MessageOut])
def get_session_messages(session_id: int):
    """Get all messages for a session (for reconnection or review)."""
    session_data = _active_sessions.get(session_id)
    if session_data is None:
        raise HTTPException(404, "Session not found.")

    return [
        MessageOut(
            role=msg.role or "system",
            agent_name=msg.agent_name,
            content=msg.content,
        )
        for msg in session_data["messages"]
    ]


@router.get("/{session_id}/status")
def get_session_status(session_id: int):
    """Check if a session is still running."""
    session_data = _active_sessions.get(session_id)
    if session_data is None:
        raise HTTPException(404, "Session not found.")

    return {
        "session_id": session_id,
        "finished": session_data["finished"],
        "message_count": len(session_data["messages"]),
    }
