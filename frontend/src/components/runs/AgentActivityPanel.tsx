// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Bot, Link, Eye, X } from "lucide-react";
import { getRunInvocations } from "../../api";
import type { AgentInvocation } from "../../types";
import InvocationDetailDrawer from "./InvocationDetailDrawer";

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "-";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
}

function statusColor(status: string): string {
  switch (status) {
    case "success":
      return "text-green-400";
    case "failed":
      return "text-red-400";
    case "running":
      return "text-blue-400";
    case "timeout":
      return "text-orange-400";
    default:
      return "text-gray-400";
  }
}

function statusBg(status: string): string {
  switch (status) {
    case "success":
      return "bg-green-900/30 border-green-700/50";
    case "failed":
      return "bg-red-900/30 border-red-700/50";
    case "running":
      return "bg-blue-900/30 border-blue-700/50";
    case "timeout":
      return "bg-orange-900/30 border-orange-700/50";
    default:
      return "bg-gray-800/30 border-gray-700/50";
  }
}

function InvocationRow({
  inv,
  onViewDetail,
  onFilterSession,
}: {
  inv: AgentInvocation;
  onViewDetail: (id: number) => void;
  onFilterSession: (sessionId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const sessionId = inv.session_id ?? (inv.metadata_?.session_id as string | undefined);

  return (
    <div className={`border rounded-lg overflow-hidden ${statusBg(inv.status)}`}>
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          className="flex items-center gap-3 flex-1 min-w-0 text-left hover:bg-white/5 transition-colors"
          onClick={() => setExpanded((v) => !v)}
        >
          <span className="text-gray-500 flex-shrink-0">
            {expanded ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
          </span>

          {/* Agent + Phase */}
          <span className="font-mono text-xs text-blue-300 flex-shrink-0 min-w-[120px]">
            {inv.agent_name}
          </span>

          {/* Phase badge */}
          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700/60 text-gray-300 flex-shrink-0">
            {inv.phase_name ?? "-"}
          </span>

          {/* Subtask title */}
          <span className="text-sm text-gray-200 flex-1 truncate">
            {inv.subtask_title
              ? inv.subtask_index !== null
                ? `[${inv.subtask_index + 1}] ${inv.subtask_title}`
                : inv.subtask_title
              : "-"}
          </span>

          {/* Cost */}
          <span className="text-xs text-amber-400 flex-shrink-0 w-16 text-right">
            {inv.estimated_cost_usd != null
              ? `$${inv.estimated_cost_usd.toFixed(4)}`
              : ""}
          </span>

          {/* Duration */}
          <span className="text-xs text-gray-400 flex-shrink-0 w-16 text-right">
            {formatDuration(inv.duration_seconds)}
          </span>

          {/* Status */}
          <span className={`text-xs font-medium flex-shrink-0 w-14 text-right ${statusColor(inv.status)}`}>
            {inv.status}
          </span>

          {/* Exit code */}
          <span className="text-xs text-gray-500 flex-shrink-0 w-10 text-right">
            {inv.exit_code !== null ? `exit ${inv.exit_code}` : ""}
          </span>
        </button>

        {/* Session badge — clickable to filter */}
        {sessionId && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onFilterSession(sessionId);
            }}
            className="hidden sm:flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-300 text-xs flex-shrink-0 hover:bg-purple-800/50 transition-colors"
            title={`Filter by session: ${sessionId}`}
          >
            <Link className="w-3 h-3" />
            <span className="font-mono">{sessionId.slice(0, 8)}</span>
          </button>
        )}

        {/* View detail button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onViewDetail(inv.id);
          }}
          className="p-1 rounded hover:bg-gray-700/50 text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0"
          title="View full prompt & response"
        >
          <Eye className="w-4 h-4" />
        </button>
      </div>

      {expanded && (
        <div className="px-4 pb-4 border-t border-white/10 space-y-3 text-sm">
          {/* Metrics row */}
          <div className="flex flex-wrap gap-4 pt-3 text-xs text-gray-400">
            <span>Prompt: {inv.prompt_chars.toLocaleString()} chars</span>
            <span>Response: {inv.response_chars.toLocaleString()} chars</span>
            {inv.estimated_tokens_in != null && (
              <span>
                Tokens: {inv.estimated_tokens_in.toLocaleString()} in / {inv.estimated_tokens_out?.toLocaleString() ?? 0} out
                {inv.metadata_?.token_source === "api" ? (
                  <span className="ml-1 text-[10px] px-1 py-0.5 rounded bg-green-900/40 text-green-400">(actual)</span>
                ) : (
                  <span className="ml-1 text-[10px] px-1 py-0.5 rounded bg-gray-700/40 text-gray-500">(est.)</span>
                )}
              </span>
            )}
            {inv.estimated_cost_usd != null && (
              <span className="text-amber-400">Cost: ${inv.estimated_cost_usd.toFixed(4)}</span>
            )}
            {inv.duration_seconds !== null && (
              <span>Duration: {formatDuration(inv.duration_seconds)}</span>
            )}
            {inv.started_at && (
              <span>Started: {new Date(inv.started_at).toLocaleTimeString()}</span>
            )}
          </div>

          {/* Session info */}
          {sessionId && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Session:</span>
              <code className="text-xs text-purple-300 font-mono bg-purple-900/20 px-1.5 py-0.5 rounded">
                {sessionId}
              </code>
            </div>
          )}

          {/* Files changed */}
          {inv.files_changed && inv.files_changed.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Files changed:</p>
              <div className="flex flex-wrap gap-1">
                {inv.files_changed.map((f) => (
                  <span
                    key={f}
                    className="px-1.5 py-0.5 bg-gray-800 text-gray-300 rounded text-xs font-mono"
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Error message */}
          {inv.error_message && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Error:</p>
              <pre className="text-xs text-red-300 bg-red-950/30 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                {inv.error_message}
              </pre>
            </div>
          )}

          {/* View detail link */}
          <button
            onClick={() => onViewDetail(inv.id)}
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            View full prompt & response →
          </button>
        </div>
      )}
    </div>
  );
}

interface Props {
  runId: number;
}

export default function AgentActivityPanel({ runId }: Props) {
  const [invocations, setInvocations] = useState<AgentInvocation[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [selectedInvocationId, setSelectedInvocationId] = useState<number | null>(null);
  const [sessionFilter, setSessionFilter] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const data = await getRunInvocations(runId, sessionFilter ?? undefined);
        if (active) setInvocations(data);
      } catch {
        // silently ignore — invocations are optional info
      }
    }

    load();
    const interval = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [runId, sessionFilter]);

  return (
    <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 mb-6 backdrop-blur-sm">
      <button
        className="w-full flex items-center gap-2 text-left mb-3"
        onClick={() => setCollapsed((v) => !v)}
      >
        <Bot className="w-4 h-4 text-gray-400 flex-shrink-0" />
        <h2 className="text-lg font-semibold flex-1">Agent Activity</h2>
        {(() => {
          const totalCost = invocations.reduce(
            (sum, inv) => sum + (inv.estimated_cost_usd ?? 0),
            0,
          );
          return totalCost > 0 ? (
            <span className="text-xs text-amber-400 mr-2">
              ${totalCost.toFixed(4)}
            </span>
          ) : null;
        })()}
        <span className="text-xs text-gray-500 mr-2">{invocations.length} invocation(s)</span>
        {collapsed ? (
          <ChevronRight className="w-4 h-4 text-gray-500" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-500" />
        )}
      </button>

      {!collapsed && (
        <>
          {/* Session filter indicator */}
          {sessionFilter && (
            <div className="flex items-center gap-2 mb-3 px-3 py-2 bg-purple-900/20 border border-purple-700/30 rounded-lg">
              <Link className="w-3.5 h-3.5 text-purple-400" />
              <span className="text-xs text-purple-300">
                Filtered by session: <code className="font-mono">{sessionFilter.slice(0, 8)}...</code>
              </span>
              <button
                onClick={() => setSessionFilter(null)}
                className="ml-auto p-0.5 rounded hover:bg-purple-800/40 text-purple-400 hover:text-purple-200 transition-colors"
                title="Clear session filter"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {invocations.length === 0 ? (
            <p className="text-sm text-gray-500">No agent invocations recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {/* Table header */}
              <div className="hidden sm:flex items-center gap-3 px-4 py-1 text-xs text-gray-500 font-medium">
                <span className="w-4 flex-shrink-0" />
                <span className="min-w-[120px]">Agent</span>
                <span className="w-16">Phase</span>
                <span className="flex-1">Subtask</span>
                <span className="w-16 text-right">Cost</span>
                <span className="w-16 text-right">Duration</span>
                <span className="w-14 text-right">Status</span>
                <span className="w-10 text-right">Exit</span>
                <span className="w-14">Session</span>
                <span className="w-6" />
              </div>
              {invocations.map((inv) => (
                <InvocationRow
                  key={inv.id}
                  inv={inv}
                  onViewDetail={setSelectedInvocationId}
                  onFilterSession={setSessionFilter}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Invocation detail drawer */}
      {selectedInvocationId !== null && (
        <InvocationDetailDrawer
          runId={runId}
          invocationId={selectedInvocationId}
          onClose={() => setSelectedInvocationId(null)}
        />
      )}
    </div>
  );
}