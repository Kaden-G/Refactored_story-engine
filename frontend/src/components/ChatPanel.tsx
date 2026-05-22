"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import type { SSEMessage } from "@/lib/api";
import {
  Crown,
  PenTool,
  BookOpen,
  User,
  Bot,
  AlertCircle,
} from "lucide-react";

const AGENT_CONFIG: Record<
  string,
  { icon: typeof Crown; color: string; bg: string }
> = {
  Director: {
    icon: Crown,
    color: "text-agent-director",
    bg: "bg-agent-director/10 border-agent-director/20",
  },
  Writer: {
    icon: PenTool,
    color: "text-agent-writer",
    bg: "bg-agent-writer/10 border-agent-writer/20",
  },
  "Lore-keeper": {
    icon: BookOpen,
    color: "text-agent-lorekeeper",
    bg: "bg-agent-lorekeeper/10 border-agent-lorekeeper/20",
  },
  System: {
    icon: Bot,
    color: "text-agent-system",
    bg: "bg-agent-system/10 border-agent-system/20",
  },
};

function getAgentConfig(agentName: string | null) {
  if (!agentName) return AGENT_CONFIG["System"];

  // Check exact match first
  if (AGENT_CONFIG[agentName]) return AGENT_CONFIG[agentName];

  // Check partial match (for NPC agents)
  const lower = agentName.toLowerCase();
  if (lower.includes("director")) return AGENT_CONFIG["Director"];
  if (lower.includes("writer")) return AGENT_CONFIG["Writer"];
  if (lower.includes("lore")) return AGENT_CONFIG["Lore-keeper"];

  // Default: NPC style
  return {
    icon: User,
    color: "text-agent-npc",
    bg: "bg-agent-npc/10 border-agent-npc/20",
  };
}

interface ChatPanelProps {
  messages: SSEMessage[];
  isStreaming: boolean;
}

export default function ChatPanel({ messages, isStreaming }: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500">
        <div className="text-center">
          <Bot className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p className="text-lg font-medium">No session running</p>
          <p className="text-sm mt-1">
            Start a session from the sidebar to begin
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
      {messages.map((msg, i) => {
        if (msg.event_type === "turn_start") {
          return (
            <div
              key={i}
              className="flex items-center gap-3 py-2 text-xs text-slate-500 uppercase tracking-wider"
            >
              <div className="flex-1 h-px bg-slate-700/50" />
              <span>Turn {msg.turn_number}</span>
              <div className="flex-1 h-px bg-slate-700/50" />
            </div>
          );
        }

        if (msg.event_type === "error") {
          return (
            <div
              key={i}
              className="message-enter flex items-start gap-3 p-4 rounded-lg border bg-red-500/10 border-red-500/20"
            >
              <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-400">Error</p>
                <p className="text-sm text-red-300/80 mt-1">{msg.content}</p>
              </div>
            </div>
          );
        }

        if (msg.event_type === "session_end") {
          return (
            <div
              key={i}
              className="flex items-center gap-3 py-4 text-sm text-slate-400"
            >
              <div className="flex-1 h-px bg-slate-700" />
              <span className="bg-surface-raised px-3 py-1 rounded-full border border-slate-700">
                Session complete
              </span>
              <div className="flex-1 h-px bg-slate-700" />
            </div>
          );
        }

        const config = getAgentConfig(msg.agent_name);
        const Icon = config.icon;

        return (
          <div
            key={i}
            className={cn(
              "message-enter flex items-start gap-3 p-4 rounded-lg border",
              config.bg
            )}
          >
            <div
              className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                config.color,
                "bg-surface-overlay"
              )}
            >
              <Icon className="w-4 h-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className={cn("text-sm font-semibold mb-1", config.color)}>
                {msg.agent_name || "System"}
              </p>
              <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                {msg.content}
              </div>
            </div>
          </div>
        );
      })}

      {isStreaming && (
        <div className="flex items-center gap-2 text-sm text-slate-500 py-2">
          <div className="flex gap-1">
            <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:300ms]" />
          </div>
          <span>Agents are working...</span>
        </div>
      )}

      <div ref={endRef} />
    </div>
  );
}
