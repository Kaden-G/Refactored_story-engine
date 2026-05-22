"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { World, Agent } from "@/lib/api";
import {
  Play,
  Square,
  Globe,
  Users,
  Scroll,
  ChevronDown,
  Zap,
} from "lucide-react";

interface SidebarProps {
  worlds: World[];
  agents: Agent[];
  selectedWorld: World | null;
  onSelectWorld: (world: World) => void;
  onStartSession: (config: {
    narrative_context: string;
    max_turns: number;
    director_agent_id: number;
  }) => void;
  onStopSession: () => void;
  isRunning: boolean;
}

export default function Sidebar({
  worlds,
  agents,
  selectedWorld,
  onSelectWorld,
  onStartSession,
  onStopSession,
  isRunning,
}: SidebarProps) {
  const [narrativeContext, setNarrativeContext] = useState(
    "Continue the Door Three search arc."
  );
  const [maxTurns, setMaxTurns] = useState(5);
  const [worldOpen, setWorldOpen] = useState(false);

  const directorAgent = agents.find(
    (a) => a.name.toLowerCase().includes("director")
  );

  const handleStart = () => {
    if (!selectedWorld || !directorAgent) return;
    onStartSession({
      narrative_context: narrativeContext,
      max_turns: maxTurns,
      director_agent_id: directorAgent.agent_id,
    });
  };

  return (
    <aside className="w-72 bg-surface-raised border-r border-slate-800 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Scroll className="w-5 h-5 text-accent" />
          <h1 className="text-base font-bold tracking-tight">
            story-engine
          </h1>
          <span className="text-[10px] text-slate-500 bg-surface-overlay px-1.5 py-0.5 rounded font-mono">
            v2
          </span>
        </div>
      </div>

      {/* World picker */}
      <div className="p-4 border-b border-slate-800">
        <label className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Globe className="w-3.5 h-3.5" />
          World
        </label>
        <div className="relative mt-2">
          <button
            onClick={() => setWorldOpen(!worldOpen)}
            className="w-full flex items-center justify-between px-3 py-2 bg-surface-overlay border border-slate-700 rounded-lg text-sm hover:border-slate-600 transition-colors"
          >
            <span>{selectedWorld?.name || "Select a world..."}</span>
            <ChevronDown
              className={cn(
                "w-4 h-4 text-slate-400 transition-transform",
                worldOpen && "rotate-180"
              )}
            />
          </button>
          {worldOpen && (
            <div className="absolute z-10 mt-1 w-full bg-surface-overlay border border-slate-700 rounded-lg shadow-xl overflow-hidden">
              {worlds.map((w) => (
                <button
                  key={w.world_id}
                  onClick={() => {
                    onSelectWorld(w);
                    setWorldOpen(false);
                  }}
                  className={cn(
                    "w-full text-left px-3 py-2 text-sm hover:bg-accent/10 transition-colors",
                    selectedWorld?.world_id === w.world_id &&
                      "bg-accent/10 text-accent"
                  )}
                >
                  {w.name}
                </button>
              ))}
              {worlds.length === 0 && (
                <p className="px-3 py-2 text-sm text-slate-500">
                  No worlds found
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Session config */}
      <div className="p-4 border-b border-slate-800 space-y-3">
        <label className="text-xs font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5" />
          Session
        </label>

        <div>
          <label className="text-xs text-slate-500 mb-1 block">
            Narrative context
          </label>
          <textarea
            value={narrativeContext}
            onChange={(e) => setNarrativeContext(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 bg-surface-overlay border border-slate-700 rounded-lg text-sm resize-none focus:outline-none focus:border-accent/50 transition-colors"
            placeholder="What should this session focus on?"
          />
        </div>

        <div>
          <label className="text-xs text-slate-500 mb-1 block">
            Max turns
          </label>
          <input
            type="number"
            min={1}
            max={20}
            value={maxTurns}
            onChange={(e) => setMaxTurns(Number(e.target.value))}
            className="w-full px-3 py-2 bg-surface-overlay border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-accent/50 transition-colors"
          />
        </div>

        {!isRunning ? (
          <button
            onClick={handleStart}
            disabled={!selectedWorld || !directorAgent}
            className={cn(
              "w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors",
              selectedWorld && directorAgent
                ? "bg-accent hover:bg-accent-hover text-white"
                : "bg-slate-800 text-slate-500 cursor-not-allowed"
            )}
          >
            <Play className="w-4 h-4" />
            Start session
          </button>
        ) : (
          <button
            onClick={onStopSession}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
          >
            <Square className="w-4 h-4" />
            Stop session
          </button>
        )}
      </div>

      {/* Agent roster */}
      <div className="p-4 flex-1 overflow-y-auto">
        <label className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
          <Users className="w-3.5 h-3.5" />
          Agents ({agents.length})
        </label>
        <div className="space-y-2 mt-2">
          {agents.map((agent) => {
            const isDirector = agent.name
              .toLowerCase()
              .includes("director");
            return (
              <div
                key={agent.agent_id}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-overlay/50 border border-slate-800"
              >
                <div
                  className={cn(
                    "w-2 h-2 rounded-full",
                    agent.is_active ? "bg-emerald-400" : "bg-slate-600"
                  )}
                />
                <span className="text-sm truncate flex-1">{agent.name}</span>
                {isDirector && (
                  <span className="text-[10px] text-agent-director bg-agent-director/10 px-1.5 py-0.5 rounded">
                    DIR
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
