// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { listServerInvocations } from "../../api";
import type { AgentInvocation } from "../../types";

const PAGE_SIZE = 20;

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "-";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${(seconds / 60).toFixed(1)}m`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const statusStyle: Record<string, string> = {
  success: "text-green-400",
  running: "text-blue-400",
  failed: "text-red-400",
  timeout: "text-yellow-400",
};

export default function ServerHistoryPanel({ serverId }: { serverId: number }) {
  const [invocations, setInvocations] = useState<AgentInvocation[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  // Filters
  const [agentFilter, setAgentFilter] = useState("");
  const [phaseFilter, setPhaseFilter] = useState("");

  const load = useCallback(
    async (reset = false) => {
      setLoading(true);
      setError(null);
      const currentOffset = reset ? 0 : offset;
      try {
        const params: Record<string, string | number> = {
          limit: PAGE_SIZE,
          offset: currentOffset,
        };
        if (agentFilter) params.agent_name = agentFilter;
        if (phaseFilter) params.phase_name = phaseFilter;

        const result = await listServerInvocations(serverId, params);
        if (reset) {
          setInvocations(result);
          setOffset(result.length);
        } else {
          setInvocations((prev) => [...(prev || []), ...result]);
          setOffset(currentOffset + result.length);
        }
        setHasMore(result.length === PAGE_SIZE);
      } catch {
        setError("Failed to load invocations");
      } finally {
        setLoading(false);
      }
    },
    [serverId, offset, agentFilter, phaseFilter],
  );

  useEffect(() => {
    setInvocations(null);
    setOffset(0);
    setHasMore(true);
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId, agentFilter, phaseFilter]);

  if (loading && !invocations) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-xs py-2">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading invocations...
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-300">Agent History</span>
        <button
          onClick={() => {
            setOffset(0);
            load(true);
          }}
          disabled={loading}
          className="text-xs text-gray-500 hover:text-gray-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Filter agent..."
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50 w-36"
        />
        <select
          value={phaseFilter}
          onChange={(e) => setPhaseFilter(e.target.value)}
          className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500/50"
        >
          <option value="">All phases</option>
          <option value="planning">Planning</option>
          <option value="coding">Coding</option>
          <option value="reviewing">Reviewing</option>
        </select>
      </div>

      {error && <p className="text-red-400 text-xs px-3 py-1">{error}</p>}

      {invocations && invocations.length === 0 && (
        <p className="text-gray-500 text-xs px-3 py-1">No invocations found.</p>
      )}

      {invocations && invocations.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-1.5 px-2 font-medium">Agent</th>
                <th className="text-left py-1.5 px-2 font-medium">Phase</th>
                <th className="text-left py-1.5 px-2 font-medium">Subtask</th>
                <th className="text-right py-1.5 px-2 font-medium">Duration</th>
                <th className="text-left py-1.5 px-2 font-medium">Status</th>
                <th className="text-right py-1.5 px-2 font-medium">Exit</th>
                <th className="text-left py-1.5 px-2 font-medium">Started</th>
                <th className="text-right py-1.5 px-2 font-medium">Run</th>
              </tr>
            </thead>
            <tbody>
              {invocations.map((inv) => (
                <tr
                  key={inv.id}
                  className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                >
                  <td className="py-1.5 px-2 text-gray-300 font-mono">{inv.agent_name}</td>
                  <td className="py-1.5 px-2 text-gray-400">{inv.phase_name || "-"}</td>
                  <td className="py-1.5 px-2 text-gray-400 max-w-[200px] truncate" title={inv.subtask_title || ""}>
                    {inv.subtask_title || "-"}
                  </td>
                  <td className="py-1.5 px-2 text-gray-400 text-right font-mono">
                    {formatDuration(inv.duration_seconds)}
                  </td>
                  <td className={`py-1.5 px-2 ${statusStyle[inv.status] || "text-gray-400"}`}>
                    {inv.status}
                  </td>
                  <td className="py-1.5 px-2 text-gray-400 text-right font-mono">
                    {inv.exit_code ?? "-"}
                  </td>
                  <td className="py-1.5 px-2 text-gray-500">{formatTime(inv.started_at)}</td>
                  <td className="py-1.5 px-2 text-right">
                    <a
                      href={`/runs/${inv.run_id}`}
                      className="text-blue-400 hover:text-blue-300 hover:underline"
                    >
                      #{inv.run_id}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasMore && invocations && invocations.length > 0 && (
        <button
          onClick={() => load(false)}
          disabled={loading}
          className="text-xs text-gray-400 hover:text-white px-3 py-1.5 rounded hover:bg-gray-700/50 transition-colors disabled:opacity-50 w-full text-center"
        >
          {loading ? "Loading..." : "Load more"}
        </button>
      )}
    </div>
  );
}