/**
 * Typed API client for the story-engine FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────

export interface World {
  world_id: number;
  name: string;
  description: string | null;
}

export interface Character {
  character_id: number;
  name: string;
  description: string | null;
  world_id: number;
}

export interface Agent {
  agent_id: number;
  name: string;
  agent_type_id: number;
  is_active: boolean;
}

export interface Location {
  location_id: number;
  name: string;
  location_type: string;
  parent_location_id: number | null;
  world_id: number;
}

export interface Belief {
  belief_id: number;
  agent_id: number;
  subject_type: string;
  subject_id: number;
  belief_content: string;
  confidence: number;
}

export interface Memory {
  memory_id: number;
  agent_id: number;
  content: string;
  confidence: number;
}

export interface Conflict {
  conflict_id: number;
  agent_1: string;
  belief_1: string;
  agent_2: string;
  belief_2: string;
}

export interface SessionConfig {
  world_id: number;
  director_agent_id: number;
  narrative_context: string;
  max_turns: number;
}

export interface SessionInfo {
  session_id: number;
  world_id: number;
  status: string;
  turn_number: number;
  narrative_context: string;
}

export interface SSEMessage {
  event_type: string;
  turn_number: number | null;
  role: string | null;
  agent_name: string | null;
  content: string;
  should_end: boolean;
}

// ── Fetch helpers ────────────────────────────────────────────────────

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// ── World queries ────────────────────────────────────────────────────

export const api = {
  getWorlds: () => fetchJSON<World[]>("/api/world/worlds"),
  getWorld: (id: number) => fetchJSON<World>(`/api/world/worlds/${id}`),
  getCharacters: (worldId: number) =>
    fetchJSON<Character[]>(`/api/world/worlds/${worldId}/characters`),
  getLocations: (worldId: number) =>
    fetchJSON<Location[]>(`/api/world/worlds/${worldId}/locations`),
  getAgents: (worldId: number) =>
    fetchJSON<Agent[]>(`/api/world/worlds/${worldId}/agents`),

  getAgentBeliefs: (agentId: number) =>
    fetchJSON<Belief[]>(`/api/world/agents/${agentId}/beliefs`),
  getAgentMemories: (agentId: number) =>
    fetchJSON<Memory[]>(`/api/world/agents/${agentId}/memories`),
  getConflicts: () => fetchJSON<Conflict[]>("/api/world/conflicts"),

  startSession: (config: SessionConfig) =>
    postJSON<SessionInfo>("/api/sessions/start", config),
};

// ── SSE stream ───────────────────────────────────────────────────────

export function streamSession(
  sessionId: number,
  onMessage: (msg: SSEMessage) => void,
  onError?: (err: Error) => void,
  onDone?: () => void,
): () => void {
  const url = `${API_BASE}/api/sessions/${sessionId}/stream`;
  const eventSource = new EventSource(url);

  const handleEvent = (event: MessageEvent) => {
    try {
      const data: SSEMessage = JSON.parse(event.data);
      onMessage(data);

      if (data.event_type === "session_end") {
        eventSource.close();
        onDone?.();
      }
    } catch (err) {
      console.error("Failed to parse SSE message:", err);
    }
  };

  eventSource.addEventListener("message", handleEvent);
  eventSource.addEventListener("turn_start", handleEvent);
  eventSource.addEventListener("session_end", handleEvent);

  eventSource.addEventListener("error", (event: MessageEvent) => {
    try {
      const data: SSEMessage = JSON.parse(event.data);
      onError?.(new Error(data.content));
    } catch {
      onError?.(new Error("SSE connection error"));
    }
    eventSource.close();
  });

  eventSource.onerror = () => {
    onError?.(new Error("SSE connection lost"));
    eventSource.close();
  };

  // Return cleanup function
  return () => {
    eventSource.close();
  };
}
