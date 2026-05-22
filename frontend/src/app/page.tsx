"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  api,
  streamSession,
  type World,
  type Agent,
  type SSEMessage,
} from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import Sidebar from "@/components/Sidebar";
import StateInspector from "@/components/StateInspector";

export default function Home() {
  const [worlds, setWorlds] = useState<World[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedWorld, setSelectedWorld] = useState<World | null>(null);
  const [messages, setMessages] = useState<SSEMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  // Load worlds on mount
  useEffect(() => {
    api
      .getWorlds()
      .then(setWorlds)
      .catch((err) => setError(`Failed to load worlds: ${err.message}`));
  }, []);

  // Load agents when world changes
  useEffect(() => {
    if (selectedWorld) {
      api
        .getAgents(selectedWorld.world_id)
        .then(setAgents)
        .catch((err) => setError(`Failed to load agents: ${err.message}`));
    } else {
      setAgents([]);
    }
  }, [selectedWorld]);

  const handleSelectWorld = useCallback((world: World) => {
    setSelectedWorld(world);
    setMessages([]);
    setError(null);
  }, []);

  const handleStartSession = useCallback(
    async (config: {
      narrative_context: string;
      max_turns: number;
      director_agent_id: number;
    }) => {
      if (!selectedWorld) return;

      setMessages([]);
      setError(null);
      setIsRunning(true);

      try {
        const session = await api.startSession({
          world_id: selectedWorld.world_id,
          ...config,
        });

        // Start SSE stream
        const cleanup = streamSession(
          session.session_id,
          (msg) => {
            setMessages((prev) => [...prev, msg]);
          },
          (err) => {
            setError(err.message);
            setIsRunning(false);
          },
          () => {
            setIsRunning(false);
          }
        );

        cleanupRef.current = cleanup;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(`Failed to start session: ${message}`);
        setIsRunning(false);
      }
    },
    [selectedWorld]
  );

  const handleStopSession = useCallback(() => {
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    setIsRunning(false);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left sidebar */}
      <Sidebar
        worlds={worlds}
        agents={agents}
        selectedWorld={selectedWorld}
        onSelectWorld={handleSelectWorld}
        onStartSession={handleStartSession}
        onStopSession={handleStopSession}
        isRunning={isRunning}
      />

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0 relative">
        {/* Top bar */}
        <header className="h-12 border-b border-slate-800 flex items-center px-6 shrink-0">
          <div className="flex items-center gap-3">
            {selectedWorld ? (
              <>
                <span className="text-sm font-medium">
                  {selectedWorld.name}
                </span>
                {isRunning && (
                  <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                    <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                    Session active
                  </span>
                )}
              </>
            ) : (
              <span className="text-sm text-slate-500">
                Select a world to begin
              </span>
            )}
          </div>

          {error && (
            <div className="ml-auto text-xs text-red-400 bg-red-500/10 px-3 py-1 rounded-full">
              {error}
            </div>
          )}
        </header>

        {/* Chat area */}
        <ChatPanel messages={messages} isStreaming={isRunning} />
      </main>

      {/* Right panel — state inspector */}
      <StateInspector
        agents={agents}
        worldId={selectedWorld?.world_id ?? null}
        isOpen={inspectorOpen}
        onToggle={() => setInspectorOpen(!inspectorOpen)}
      />
    </div>
  );
}
