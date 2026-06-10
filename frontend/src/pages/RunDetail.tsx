// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ExternalLink, FileText, RefreshCcw, RotateCw, Terminal, XCircle } from "lucide-react";
import {
  cancelRun,
  getRun,
  restartRun,
  retryRun,
} from "../api";
import AgentActivityPanel from "../components/runs/AgentActivityPanel";
import RunCostSummary from "../components/runs/RunCostSummary";
import ApprovalButtons from "../components/runs/ApprovalButtons";
import CodingResultsPanel from "../components/runs/CodingResultsPanel";
import CollapsibleJSON from "../components/shared/CollapsibleJSON";
import Info from "../components/shared/Info";
import ReviewResultPanel from "../components/runs/ReviewResultPanel";
import LogViewer from "../components/runs/LogViewer";
import PhaseTimeline from "../components/runs/PhaseTimeline";
import RunTerminalDrawer from "../components/runs/RunTerminalDrawer";
import StatusBadge from "../components/shared/StatusBadge";
import SafeHtml from "../components/shared/SafeHtml";
import type { TaskRunDetail as TRD } from "../types";

export default function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const runId = Number(id);
  const [run, setRun] = useState<TRD | null>(null);
  const [terminalOpen, setTerminalOpen] = useState(false);

  const load = useCallback(async () => {
    const r = await getRun(runId);
    setRun(r);
  }, [runId]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  if (!run) return <p className="text-gray-500">Loading...</p>;

  const meta = run.task_source_meta as Record<string, unknown> | undefined;
  const labels: string[] = Array.isArray(meta?.labels)
    ? (meta!.labels as string[])
    : [];
  const sourcePrUrl = (meta?.pr_url as string) || null;
  const sourcePrNumber = (meta?.pr_number as number) || null;

  return (
    <>
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <h1 className="text-xl font-semibold">{run.title}</h1>
        <StatusBadge status={run.status} />
      </div>

      {/* Description */}
      {run.description && (
        <SafeHtml
          html={run.description}
          className="text-gray-400 text-sm mb-6 -mt-4 prose prose-sm prose-invert max-w-none"
        />
      )}

      {/* Labels */}
      {labels.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {labels.map((l) => (
            <span key={l} className="px-2 py-0.5 bg-blue-900/40 text-blue-300 rounded text-xs">{l}</span>
          ))}
        </div>
      )}

      {/* Current step */}
      <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 mb-6 backdrop-blur-sm">
        <PhaseTimeline currentPhase={run.current_phase} status={run.status} />
      </div>

      {/* Info Grid */}
      <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 mb-6 backdrop-blur-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <Info label="Task ID" value={run.task_id} />
          <Info label="Run Type" value={run.run_type} />
          <Info label="Project" value={run.project_id} />
          <Info label="Repository" value={`${run.repo_owner}/${run.repo_name}`} />
          <Info label="Branch" value={run.branch_name} />
          <Info label="Default Branch" value={run.default_branch} />
          <Info label="Source" value={`${run.task_source} / ${run.git_provider}`} />
          <Info label="Workspace" value={run.workspace_path} />
          <Info label="Retries" value={`${run.retry_count} / ${run.max_retries ?? 3}`} />
          {run.use_claude_api && <Info label="Claude API" value="Yes" />}
          {sourcePrUrl && (
            <Info
              label="Source PR"
              value={
                <a href={sourcePrUrl} target="_blank" rel="noreferrer" className="text-blue-400 hover:text-blue-300 hover:underline inline-flex items-center gap-1.5">
                  <ExternalLink className="w-3.5 h-3.5" />
                  PR #{sourcePrNumber ?? ""}
                </a>
              }
            />
          )}
          {run.pr_url && (
            <Info
              label="PR"
              value={
                <a href={run.pr_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:text-blue-300 hover:underline">
                  {run.pr_url}
                </a>
              }
            />
          )}
          {run.parent_run_id && (
            <Info
              label="Parent Run"
              value={
                <Link to={`/runs/${run.parent_run_id}`} className="text-blue-400 hover:text-blue-300 hover:underline">
                  Run #{run.parent_run_id}
                </Link>
              }
            />
          )}
          {run.error_message && <Info label="Error" value={<span className="text-red-400">{run.error_message}</span>} />}
          <Info label="Created" value={formatDateTime(run.created_at)} />
          {run.started_at && <Info label="Started" value={formatDateTime(run.started_at)} />}
          {run.completed_at && <Info label="Completed" value={formatDateTime(run.completed_at)} />}
          {run.started_at && run.completed_at && (
            <Info label="Duration" value={formatPhaseDuration(run.started_at, run.completed_at)} />
          )}
          {run.approval_requested_at && (
            <Info label="Approval Requested" value={formatDateTime(run.approval_requested_at)} />
          )}
        </div>
      </div>

      {/* Task Source Metadata */}
      {run.task_source_meta && Object.keys(run.task_source_meta).length > 0 && (
        <CollapsibleJSON title="Task Source Metadata" data={run.task_source_meta} defaultOpen={false} />
      )}

      {/* Actions */}
      {(run.status === "awaiting_approval" || ["failed", "cancelled", "timeout", "pending", "running", "completed", "waiting_for_trigger"].includes(run.status)) && (
        <div className="flex flex-wrap gap-3 mb-6">
          {run.status === "awaiting_approval" && run.approved === null && (
            <ApprovalButtons runId={runId} onAction={load} />
          )}
          {["failed", "cancelled", "timeout"].includes(run.status) && (
            <button
              onClick={async () => { await retryRun(runId); load(); }}
              className="px-4 py-1.5 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg text-sm inline-flex items-center gap-1.5 shadow-sm shadow-yellow-900/30 focus:outline-none focus:ring-2 focus:ring-yellow-500/40"
            >
              <RotateCw className="w-4 h-4" />
              Retry
            </button>
          )}
          {!["pending", "running"].includes(run.status) && (
            <button
              onClick={async () => { await restartRun(runId); load(); }}
              className="px-4 py-1.5 bg-orange-700 hover:bg-orange-600 text-white rounded-lg text-sm inline-flex items-center gap-1.5 shadow-sm shadow-orange-900/30 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
            >
              <RefreshCcw className="w-4 h-4" />
              Restart
            </button>
          )}
          {["pending", "running"].includes(run.status) && (
            <button
              onClick={async () => { await cancelRun(runId); load(); }}
              className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm inline-flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-gray-500/40"
            >
              <XCircle className="w-4 h-4" />
              Cancel
            </button>
          )}
          {["completed", "failed", "awaiting_approval", "timeout", "cancelled", "waiting_for_trigger"].includes(run.status) && (
            <button
              onClick={() => setTerminalOpen(true)}
              className="px-4 py-1.5 bg-green-700 hover:bg-green-600 text-white rounded-lg text-sm inline-flex items-center gap-1.5 shadow-sm shadow-green-900/30 focus:outline-none focus:ring-2 focus:ring-green-500/40"
            >
              <Terminal className="w-4 h-4" />
              Continue in Terminal
            </button>
          )}
        </div>
      )}

      {/* Logs */}
      <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 mb-6 backdrop-blur-sm">
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4 text-gray-400" />
          Logs
        </h2>
        <LogViewer runId={runId} phase={null} />
      </div>

      {/* Cost Summary */}
      <RunCostSummary runId={runId} />

      {/* Agent Activity */}
      <AgentActivityPanel runId={runId} />

      {/* Run results */}
      {run.coding_results && (
        <CodingResultsPanel data={run.coding_results as Record<string, unknown>} />
      )}
      {run.review_result && (
        <ReviewResultPanel data={run.review_result as Record<string, unknown>} />
      )}

      {/* Terminal Drawer */}
      {terminalOpen && (
        <RunTerminalDrawer
          runId={runId}
          workspacePath={run.workspace_path}
          onClose={() => setTerminalOpen(false)}
          onAction={load}
        />
      )}
    </>
  );
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString();
}

function formatPhaseDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
}
