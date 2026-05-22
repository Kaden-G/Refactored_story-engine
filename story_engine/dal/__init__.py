"""Data-access layer — thin bridge between Python and the MAMS database."""

from story_engine.dal.connection import get_pool, close_pool
from story_engine.dal.mams_dal import MamsDAL

__all__ = ["get_pool", "close_pool", "MamsDAL"]
