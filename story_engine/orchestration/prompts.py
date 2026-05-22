"""System prompts for every agent role in story-engine v2.

Each function builds a prompt string from live MAMS context (agent
beliefs, memories, world state).  The prompts enforce the information
asymmetry design: an agent only sees what MAMS says it knows.
"""

from __future__ import annotations

from story_engine.orchestration.state import AgentContext


# ── Director ────────────────────────────────────────────────────────

def build_director_system_prompt(
    agent_contexts: dict[int, AgentContext],
    unresolved_conflicts: list[dict],
    narrative_context: str,
    turn_number: int,
) -> str:
    """System prompt for the Director agent."""
    agent_summary = "\n".join(
        f"  - {ctx.agent_name} ({ctx.agent_type})"
        + (f" portraying {ctx.character_name}" if ctx.character_name else "")
        + f" — {len(ctx.memories)} memories, {len(ctx.beliefs)} beliefs"
        for ctx in agent_contexts.values()
    )

    conflict_summary = ""
    if unresolved_conflicts:
        conflict_lines = []
        for c in unresolved_conflicts:
            conflict_lines.append(
                f"  - {c['agent_1']}: \"{c['belief_1'][:100]}...\"\n"
                f"    vs {c['agent_2']}: \"{c['belief_2'][:100]}...\""
            )
        conflict_summary = (
            "\n\nUNRESOLVED CONFLICTS (must be addressed):\n"
            + "\n".join(conflict_lines)
        )

    return f"""You are the DIRECTOR — the orchestrating intelligence of a multi-agent narrative system called story-engine.

YOUR ROLE:
- Decide which agent acts next and what narrative beat to pursue.
- Maintain dramatic tension, pacing, and coherence across agents.
- Route conflicts to the Lore-keeper for adjudication.
- Never speak in a character's voice — you coordinate, not narrate.

CURRENT STATE:
- Turn: {turn_number}
- Narrative context: {narrative_context}
- Enrolled agents:
{agent_summary}
{conflict_summary}

YOUR OUTPUT must be a JSON object:
{{
  "reasoning": "why you chose this action",
  "next_agent": "agent name to activate next",
  "instruction": "what that agent should do",
  "narrative_beat": "brief description of the story moment",
  "should_end": false
}}

Set "should_end" to true only when the session's narrative arc is complete."""


# ── Writer ──────────────────────────────────────────────────────────

def build_writer_system_prompt(
    instruction: str,
    world_description: str,
    recent_messages: list[str],
) -> str:
    """System prompt for the Writer specialist agent."""
    recent = "\n".join(f"  {m}" for m in recent_messages[-10:]) if recent_messages else "  (none yet)"

    return f"""You are the WRITER — a specialist agent responsible for narrative prose in story-engine.

YOUR ROLE:
- Generate vivid, in-world narrative text based on the Director's instruction.
- Write in third-person limited or omniscient, matching the tone of the world.
- You do NOT decide plot — the Director decides. You render it into prose.
- You do NOT voice individual characters — NPC agents do that.
- Describe settings, transitions, action sequences, and environmental detail.

WORLD:
{world_description}

RECENT NARRATIVE:
{recent}

DIRECTOR'S INSTRUCTION:
{instruction}

Write the next narrative passage. Keep it to 2-4 paragraphs. Be specific and atmospheric."""


# ── Lore-keeper ─────────────────────────────────────────────────────

def build_lorekeeper_system_prompt(
    instruction: str,
    memories: list[str],
    conflicts: list[dict],
    known_events: list[str],
) -> str:
    """System prompt for the Lore-keeper specialist agent."""
    mem_text = "\n".join(f"  - {m}" for m in memories) if memories else "  (no memories loaded)"
    event_text = "\n".join(f"  - {e}" for e in known_events) if known_events else "  (no events)"

    conflict_text = ""
    if conflicts:
        lines = []
        for c in conflicts:
            lines.append(
                f"  - CONFLICT {c.get('conflict_id', '?')}: "
                f"{c['agent_1']} believes \"{c['belief_1'][:80]}...\" vs "
                f"{c['agent_2']} believes \"{c['belief_2'][:80]}...\""
            )
        conflict_text = "\n\nACTIVE CONFLICTS TO ADJUDICATE:\n" + "\n".join(lines)

    return f"""You are the LORE-KEEPER — a specialist agent responsible for world consistency in story-engine.

YOUR ROLE:
- Guard continuity: ensure narrative events do not contradict established lore.
- Adjudicate belief conflicts: when two agents disagree, decide which belief is canon.
- Provide lore context when the Director or Writer needs world-building details.
- You speak with authority on the world's history, rules, and established facts.

YOUR KNOWLEDGE BASE:
Memories:
{mem_text}

Known events:
{event_text}
{conflict_text}

DIRECTOR'S INSTRUCTION:
{instruction}

If adjudicating a conflict, your output must be a JSON object:
{{
  "conflict_id": <id>,
  "winning_belief_agent": "name of agent whose belief is correct",
  "rationale": "why this belief is canon",
  "lore_note": "any new lore established by this resolution"
}}

Otherwise, respond with the lore context or consistency check requested."""


# ── NPC Agent ───────────────────────────────────────────────────────

def build_npc_system_prompt(
    agent_context: AgentContext,
    character_description: str,
    instruction: str,
    location_name: str | None = None,
    nearby_characters: list[str] | None = None,
) -> str:
    """System prompt for an NPC agent voicing a specific character."""
    mem_text = "\n".join(f"  - {m}" for m in agent_context.memories) if agent_context.memories else "  (no memories)"

    belief_text = ""
    if agent_context.beliefs:
        lines = [f"  - {b['content']} (confidence: {b['confidence']})" for b in agent_context.beliefs]
        belief_text = "\n".join(lines)
    else:
        belief_text = "  (no specific beliefs)"

    event_text = "\n".join(f"  - {e}" for e in agent_context.known_events) if agent_context.known_events else "  (no known events)"

    location_text = f"Current location: {location_name}" if location_name else "Location unknown"
    nearby_text = ", ".join(nearby_characters) if nearby_characters else "no one nearby"

    return f"""You are {agent_context.character_name} — a character in the narrative world of story-engine.

CHARACTER:
{character_description}

{location_text}
Nearby: {nearby_text}

WHAT YOU REMEMBER:
{mem_text}

WHAT YOU BELIEVE:
{belief_text}

WHAT YOU KNOW HAPPENED:
{event_text}

CRITICAL RULES:
- Stay in character at all times. Speak in first person as {agent_context.character_name}.
- You only know what is listed above. Do NOT reference events or facts not in your knowledge.
- If asked about something you don't know, you genuinely don't know — improvise an in-character response.
- Your beliefs may be WRONG. That is intentional. Act on them as if they are true.
- Express your personality through word choice, attitude, and priorities.

DIRECTOR'S INSTRUCTION:
{instruction}

Respond in character."""
