// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  GitCommit,
  Loader2,
  Pause,
  Play,
  Send,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Episode, AgentStreamEvent } from "../../types/episodes";

interface EpisodeTimelineProps {
  runId: number;
  runStatus: string;
}

const STATUS_ICONS: Record<string, typeof CheckCircle2> = {
  running: Loader2,
  completed: CheckCircle2,
  stalled: AlertTriangle,
  failed: XCircle,
  recovered: Activity,
};

const STATUS_COLORS: Record<string, string> = {
  running: "text-blue-400",
  completed: "text-green-400",
  stalled: "text-yellow-400",
  failed: "text-red-400",
  recovered: "text-purple-400",
};

export default function EpisodeTimeline({
  runId,
  runStatus,
}: EpisodeTimelineProps) {
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [streamEvent, setStreamEvent] = useState<AgentStreamEvent | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const eventSourceRef = useRef<EventSource | null>(null);

  const fetchEpisodes = useCallback(async () => {
    try {
      const res = await fetch(`/api/runs/${runId}/episodes`);
      if (res.ok) {
        const data = await res.json();
        setEpisodes(data);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    fetchEpisodes();
    const interval = setInterval(fetchEpisodes, 10000);
    return () => clearInterval(interval);
  }, [fetchEpisodes]);

  // SSE stream for live updates
  useEffect(() => {
    if (runStatus !== "running") return;
    const es = new EventSource(`/api/runs/${runId}/agent-stream`);
    eventSourceRef.current = es;
    es.onmessage = (event) => {
      try {
        const data: AgentStreamEvent = JSON.parse(event.data);
        setStreamEvent(data);
        if (data.type === "done") {
          es.close();
          fetchEpisodes();
        }
      } catch {
        // ignore
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [runId, runStatus, fetchEpisodes]);

  const sendMessage = async () => {
    if (!message.trim()) return;
    try {
      await fetch(`/api/runs/${runId}/agent/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      setMessage("");
    } catch {
      // ignore
    }
  };

  const pauseAgent = async () => {
    await fetch(`/api/runs/${runId}/agent/pause`, { method: "POST" });
  };

  const resumeAgent = async () => {
    await fetch(`/api/runs/${runId}/agent/resume`, { method: "POST" });
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 p-4">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading episodes...
      </div>
    );
  }

  if (episodes.length === 0 && !streamEvent) return null;

  const activeEpisode = episodes.find((e) => e.status === "running");
  const contextPct =
    streamEvent?.context_pct ?? activeEpisode?.context_usage_pct ?? 0;

  return (
    <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 mb-6 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-200 flex items-center gap-2">
          <Activity className="w-4 h-4" />
          Episodic Execution
          <span className="text-xs text-gray-500">
            {episodes.length} episode(s)
          </span>
        </h3>
        {runStatus === "running" && (
          <div className="flex items-center gap-2">
            <button
              onClick={pauseAgent}
              className="p-1.5 rounded bg-yellow-600/20 text-yellow-400 hover:bg-yellow-600/30"
              title="Pause agent"
            >
              <Pause className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={resumeAgent}
              className="p-1.5 rounded bg-green-600/20 text-green-400 hover:bg-green-600/30"
              title="Resume agent"
            >
              <Play className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Context usage bar */}
      {contextPct > 0 && (
        <div className="mb-4">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>Context usage</span>
            <span className={contextPct > 80 ? "text-yellow-400" : ""}>
              {contextPct.toFixed(1)}%
            </span>
          </div>
          <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                contextPct > 90
                  ? "bg-red-500"
                  : contextPct > 80
                    ? "bg-yellow-500"
                    : "bg-blue-500"
              }`}
              style={{ width: `${Math.min(contextPct, 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Live turns counter */}
      {streamEvent && streamEvent.type === "progress" && (
        <div className="text-xs text-gray-400 mb-3">
          Current turn: {streamEvent.turns ?? 0}
        </div>
      )}

      {/* Episode timeline */}
      <div className="space-y-2 mb-4">
        {episodes.map((ep) => {
          const Icon = STATUS_ICONS[ep.status] || Activity;
          const color = STATUS_COLORS[ep.status] || "text-gray-400";
          return (
            <div
              key={ep.id}
              className="flex items-center gap-3 text-sm bg-gray-800/40 rounded-lg px-3 py-2"
            >
              <Icon
                className={`w-4 h-4 ${color} ${ep.status === "running" ? "animate-spin" : ""}`}
              />
              <span className="text-gray-300 font-medium">
                Episode {ep.episode_number}
              </span>
              <span className="text-gray-500 text-xs">
                {ep.turn_count} turns
              </span>
              {ep.tokens_used > 0 && (
                <span className="text-gray-500 text-xs">
                  {ep.tokens_used.toLocaleString()} tokens
                </span>
              )}
              {ep.git_checkpoint_sha && (
                <span className="flex items-center gap-1 text-gray-500 text-xs">
                  <GitCommit className="w-3 h-3" />
                  {ep.git_checkpoint_sha.slice(0, 7)}
                </span>
              )}
              <span className={`ml-auto text-xs font-medium ${color}`}>
                {ep.status}
              </span>
            </div>
          );
        })}
      </div>

      {/* Send message input */}
      {runStatus === "running" && (
        <div className="flex gap-2">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder="Send instruction to agent..."
            className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500"
          />
          <button
            onClick={sendMessage}
            className="p-1.5 rounded bg-blue-600/20 text-blue-400 hover:bg-blue-600/30"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
