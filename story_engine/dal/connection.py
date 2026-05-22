"""Connection pool management for the MAMS database.

Uses psycopg 3's ConnectionPool.  Configuration comes from environment
variables (loaded via python-dotenv).  Call get_pool() to obtain the
singleton pool; call close_pool() at shutdown.
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()

_pool: Optional[ConnectionPool] = None


def _build_conninfo() -> str:
    """Assemble a libpq connection string from environment variables."""
    host = os.getenv("MAMS_DB_HOST", "localhost")
    port = os.getenv("MAMS_DB_PORT", "5432")
    dbname = os.getenv("MAMS_DB_NAME", "mams")
    user = os.getenv("MAMS_DB_USER", "postgres")
    password = os.getenv("MAMS_DB_PASSWORD", "")
    parts = [
        f"host={host}",
        f"port={port}",
        f"dbname={dbname}",
        f"user={user}",
    ]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


def get_pool(
    min_size: int = 2,
    max_size: int = 10,
    conninfo: str | None = None,
) -> ConnectionPool:
    """Return the singleton connection pool, creating it on first call.

    Parameters
    ----------
    min_size : int
        Minimum number of connections kept open.
    max_size : int
        Maximum number of connections the pool will open.
    conninfo : str | None
        Override connection string.  If *None*, built from env vars.
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=conninfo or _build_conninfo(),
            min_size=min_size,
            max_size=max_size,
            open=True,
        )
    return _pool


def close_pool() -> None:
    """Close the connection pool.  Safe to call even if never opened."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
