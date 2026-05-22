"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import {
  api,
  type Agent,
  type Belief,
  type Memory,
  type Conflict,
} from "@/lib/api";
import {
  Brain,
  Eye,
  Swords,
  ChevronRight,
  RefreshCw,
} from "lucide-react";

interface StateInspectorProps {
  agents: Agent[];
  worldId: number | null;
  isOpen: boolean;
  onToggle: () => void;
}

export default function StateInspector({
  agents,
  worldId,
  isOpen,
  onToggle,
}: StateInspectorProps) {
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [beliefs, setBeliefs] = useState<Belief[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"beliefs" | "memories" | "conflicts">("beliefs");

  const loadAgentState = async (agent: Agent) => {
    setSelectedAgent(agent);
    setLoading(true);
    try {
      const [b, m] = await Promise.all([
        api.getAgentBeliefs(agent.agent_id),
        api.getAgentMemories(agent.agent_id),
      ]);
      setBeliefs(b);
      setMemories(m);
    } catch (err) {
      console.error("Failed to load agent state:", err);
    }
    setLoading(false);
  };

  const loadConflicts = async () => {
    try {
      const c = await api.getConflicts();
      setConflicts(c);
    } catch (err) {
      console.error("Failed to load conflicts:", err);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadConflicts();
    }
  }, [isOpen]);

  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="absolute right-0 top-1/2 -translate-y-1/2 bg-surface-raised border border-slate-800 border-r-0 rounded-l-lg p-2 hover:bg-surface-overlay transition-colors"
        title="Open state inspector"
      >
        <Eye className="w-4 h-4 text-slate-400" />
      </button>
    );
  }

  return (
    <aside className="w-80 bg-surface-raised border-l border-slate-800 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Eye className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-semibold">State Inspector</h2>
        </div>
        <button
          onClick={onToggle}
          className="text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {/* Agent selector */}
      <div className="p-3 border-b border-slate-800">
        <label className="text-xs text-slate-500 mb-2 block">
          Inspect agent
        </label>
        <div className="flex flex-wrap gap-1.5">
          {agents.map((agent) => (
            <button
              key={agent.agent_id}
              onClick={() => loadAgentState(agent)}
              className={cn(
                "px-2 py-1 rounded text-xs transition-colors",
                selectedAgent?.agent_id === agent.agent_id
                  ? "bg-accent/20 text-accent border border-accent/30"
                  : "bg-surface-overlay text-slate-400 border border-slate-700 hover:border-slate-600"
              )}
            >
              {agent.name.split(" ")[0]}
            </button>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800">
        {(["beliefs", "memories", "conflicts"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => {
              setActiveTab(tab);
              if (tab === "conflicts") loadConflicts();
            }}
            className={cn(
              "flex-1 px-3 py-2 text-xs font-medium capitalize transition-colors",
              activeTab === tab
                ? "text-accent border-b-2 border-accent"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            {tab}
            {tab === "beliefs" && beliefs.length > 0 && (
              <span className="ml-1 text-[10px] opacity-60">
                ({beliefs.length})
              </span>
            )}
            {tab === "memories" && memories.length > 0 && (
              <span className="ml-1 text-[10px] opacity-60">
                ({memories.length})
              </span>
            )}
            {tab === "conflicts" && conflicts.length > 0 && (
              <span className="ml-1 text-[10px] text-red-400">
                ({conflicts.length})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="w-5 h-5 text-slate-500 animate-spin" />
          </div>
        )}

        {!loading && activeTab === "beliefs" && (
          <>
            {beliefs.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-4">
                {selectedAgent
                  ? "No beliefs found"
                  : "Select an agent to inspect"}
              </p>
            ) : (
              beliefs.map((b) => (
                <div
                  key={b.belief_id}
                  className="p-3 bg-surface-overlay rounded-lg border border-slate-800"
                >
                  <div className="flex items-start gap-2">
                    <Brain className="w-3.5 h-3.5 text-agent-lorekeeper shrink-0 mt-0.5" />
                    <div className="min-w-0">
                      <p className="text-xs text-slate-300 leading-relaxed">
                        {b.belief_content}
                      </p>
                      <div className="flex items-center gap-3 mt-1.5">
                        <span className="text-[10px] text-slate-500">
                          {b.subject_type}#{b.subject_id}
                        </span>
                        <span
                          className={cn(
                            "text-[10px] font-medium",
                            b.confidence >= 0.8
                              ? "text-emerald-400"
                              : b.confidence >= 0.5
                              ? "text-yellow-400"
                              : "text-red-400"
                          )}
                        >
                          {(b.confidence * 100).toFixed(0)}% confidence
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </>
        )}

        {!loading && activeTab === "memories" && (
          <>
            {memories.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-4">
                {selectedAgent
                  ? "No memories found"
                  : "Select an agent to inspect"}
              </p>
            ) : (
              memories.map((m) => (
                <div
                  key={m.memory_id}
                  className="p-3 bg-surface-overlay rounded-lg border border-slate-800"
                >
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {m.content}
                  </p>
                  <span
                    className={cn(
                      "text-[10px] font-medium mt-1 inline-block",
                      m.confidence >= 0.8
                        ? "text-emerald-400"
                        : "text-yellow-400"
                    )}
                  >
                    {(m.confidence * 100).toFixed(0)}% confidence
                  </span>
                </div>
              ))
            )}
          </>
        )}

        {!loading && activeTab === "conflicts" && (
          <>
            {conflicts.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-4">
                No unresolved conflicts
              </p>
            ) : (
              conflicts.map((c) => (
                <div
                  key={c.conflict_id}
                  className="p-3 bg-red-500/5 rounded-lg border border-red-500/20"
                >
                  <div className="flex items-center gap-1.5 mb-2">
                    <Swords className="w-3.5 h-3.5 text-red-400" />
                    <span className="text-xs font-medium text-red-400">
                      Conflict #{c.conflict_id}
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    <div className="text-xs">
                      <span className="text-slate-400">{c.agent_1}:</span>{" "}
                      <span className="text-slate-300">
                        &ldquo;{c.belief_1}&rdquo;
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-600 text-center">
                      vs
                    </div>
                    <div className="text-xs">
                      <span className="text-slate-400">{c.agent_2}:</span>{" "}
                      <span className="text-slate-300">
                        &ldquo;{c.belief_2}&rdquo;
                      </span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </>
        )}
      </div>
    </aside>
  );
}
