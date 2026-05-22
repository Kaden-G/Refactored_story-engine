"""FastAPI backend for story-engine v2.

Serves the REST + SSE API for the Next.js frontend.
Manages the psycopg connection pool lifecycle.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from story_engine.dal import get_pool, close_pool, MamsDAL

from api.routes.world import router as world_router
from api.routes.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the DB pool on startup, close on shutdown."""
    pool = get_pool()
    app.state.pool = pool
    app.state.dal = MamsDAL(pool)
    yield
    close_pool()


app = FastAPI(
    title="story-engine v2",
    version="2.0.0a1",
    lifespan=lifespan,
)

# CORS — allow the Next.js dev server and production origins
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
custom_origin = os.getenv("FRONTEND_ORIGIN")
if custom_origin:
    origins.append(custom_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(world_router, prefix="/api/world", tags=["world"])
app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
