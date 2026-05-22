"""Session management and SSE streaming routes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from api.schemas import MessageOut, SessionOut, SessionStartRequest, SSEMessage

router = APIRouter()
log = logging.getLogger(__name__)

# In-memory store for active sessions (single-process; fine for MVP)
_active_sessions: dict[int, dict] = {}


def _dal(request: Request):
    return request.app.state.dal


def _get_llm():
    """Build an LLM if an API key is available."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-sonnet-4-20250514", api_key=api_key)
    return None


@router.post("/start", response_model=SessionOut)
def start_session(body: SessionStartRequest, request: Request):
    """Start a new Director session and return session metadata."""
    dal = _dal(request)

    from story_engine.orchestration import build_director_graph

    llm = _get_llm()
    graph = build_director_graph(dal, llm=llm, max_turns=body.max_turns)

    # Initial state for LangGraph
    initial_state = {
        "world_id": body.world_id,
        "director_agent_id": body.director_agent_id,
        "narrative_context": body.narrative_context,
    }

    # Store the graph and state for stepping or streaming
    # We'll use a simple counter for session IDs here;
    # the real MAMS session_id comes after open_session runs.
    temp_id = id(graph)  # temporary until MAMS assigns one
    _active_sessions[temp_id] = {
        "graph": graph,
        "initial_state": initial_state,
        "body": body,
        "state": None,  # populated after first step
        "messages": [],
        "finished": False,
    }

    return SessionOut(
        session_id=temp_id,
        world_id=body.world_id,
        status="created",
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
