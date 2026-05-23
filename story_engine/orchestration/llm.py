"""Helpers for wiring up the LLM backing the orchestration layer.

Centralises the model id so it lives in one place (the
STORY_ENGINE_MODEL env var, defaulting to a reasonable Claude model).
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def build_llm():
    """Return a LangChain chat model, or None if no API key is set.

    Reads ANTHROPIC_API_KEY and STORY_ENGINE_MODEL from the
    environment. Callers can pass the result straight to
    build_director_graph(llm=...).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    from langchain_anthropic import ChatAnthropic
    model = os.getenv("STORY_ENGINE_MODEL", DEFAULT_MODEL)
    return ChatAnthropic(model=model, api_key=api_key)
