// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { ArrowDown, ArrowUp, ArrowUpDown, Clock, DollarSign, Inbox } from "lucide-react";
import { Link } from "react-router-dom";
import type { TaskRun } from "../../types";
import StatusBadge from "../shared/StatusBadge";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatDuration(startedAt: string | null, completedAt: string | null, status: string): string | null {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : (status === "running" ? Date.now() : null);
  if (!end) return null;
  const totalSeconds = Math.round((end - start) / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function formatCost(cost: number | null): string | null {
  if (cost == null) return null;
  if (cost < 0.01) return "<$0.01";
  return `$${cost.toFixed(2)}`;
}

interface Props {
  runs: TaskRun[];
  workflowNames?: Map<number, string>;
  sortBy?: string;
  sortOrder?: string;
  onSort?: (column: string) => void;
}

function SortIcon({ column, sortBy, sortOrder }: { column: string; sortBy?: string; sortOrder?: string }) {
  if (sortBy !== column) return <ArrowUpDown className="w-3 h-3 opacity-30" />;
  return sortOrder === "asc" ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />;
}

export default function TaskRunTable({ runs, workflowNames, sortBy, sortOrder, onSort }: Props) {
  if (!runs.length)
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-500 bg-gray-900/40 border border-gray-800/60 rounded-xl backdrop-blur-sm">
        <Inbox className="w-8 h-8 mb-2 text-gray-600" />
        <p>No runs found.</p>
      </div>
    );

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/60 bg-gray-900/40 backdrop-blur-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800/60 text-left bg-gray-800/40">
            <th className="py-2.5 pr-4 pl-4 text-gray-500 font-medium text-xs uppercase tracking-wider">#</th>
            <th
              className="py-2.5 pr-4 text-gray-500 font-medium text-xs uppercase tracking-wider cursor-pointer hover:text-gray-300 select-none"
              onClick={() => onSort?.("title")}
            >
              <span className="inline-flex items-center gap-1">
                Title {onSort && <SortIcon column="title" sortBy={sortBy} sortOrder={sortOrder} />}
              </span>
            </th>
            <th className="py-2.5 pr-4 hidden sm:table-cell text-gray-500 font-medium text-xs uppercase tracking-wider">Project</th>
            <th
              className="py-2.5 pr-4 text-gray-500 font-medium text-xs uppercase tracking-wider cursor-pointer hover:text-gray-300 select-none"
              onClick={() => onSort?.("status")}
            >
              <span className="inline-flex items-center gap-1">
                Status {onSort && <SortIcon column="status" sortBy={sortBy} sortOrder={sortOrder} />}
              </span>
            </th>
            <th className="py-2.5 pr-4 text-gray-500 font-medium text-xs uppercase tracking-wider">Phase</th>
            <th className="py-2.5 pr-4 hidden md:table-cell text-gray-500 font-medium text-xs uppercase tracking-wider">
              <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3" />Duration</span>
            </th>
            <th className="py-2.5 pr-4 hidden md:table-cell text-gray-500 font-medium text-xs uppercase tracking-wider">
              <span className="inline-flex items-center gap-1"><DollarSign className="w-3 h-3" />Cost</span>
            </th>
            <th className="py-2.5 pr-4 hidden sm:table-cell text-gray-500 font-medium text-xs uppercase tracking-wider">Workflow</th>
            <th
              className="py-2.5 hidden sm:table-cell text-gray-500 font-medium text-xs uppercase tracking-wider cursor-pointer hover:text-gray-300 select-none"
              onClick={() => onSort?.("created_at")}
            >
              <span className="inline-flex items-center gap-1">
                Created {onSort && <SortIcon column="created_at" sortBy={sortBy} sortOrder={sortOrder} />}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const duration = formatDuration(r.started_at, r.completed_at, r.status);
            const cost = formatCost(r.total_cost_usd);
            return (
              <tr
                key={r.id}
                className="border-b border-gray-800/30 hover:bg-gray-800/40 transition-colors"
              >
                <td className="py-2.5 pr-4 pl-4 text-gray-500 font-mono text-xs">{r.id}</td>
                <td className="py-2.5 pr-4">
                  <Link
                    to={`/runs/${r.id}`}
                    className="text-blue-400 hover:text-blue-300 hover:underline"
                  >
                    {r.title}
                  </Link>
                </td>
                <td className="py-2.5 pr-4 text-gray-400 hidden sm:table-cell">
                  {r.project_id}
                </td>
                <td className="py-2.5 pr-4">
                  <StatusBadge status={r.status} />
                </td>
                <td className="py-2.5 pr-4 text-gray-400">
                  {r.current_phase ?? "—"}
                </td>
                <td className="py-2.5 pr-4 text-gray-400 hidden md:table-cell font-mono text-xs">
                  {duration ?? "—"}
                </td>
                <td className="py-2.5 pr-4 hidden md:table-cell font-mono text-xs">
                  {cost ? (
                    <span className="text-green-400">{cost}</span>
                  ) : "—"}
                </td>
                <td className="py-2.5 pr-4 text-gray-400 hidden sm:table-cell">
                  {r.workflow_template_id
                    ? (workflowNames?.get(r.workflow_template_id) ?? "—")
                    : "—"}
                </td>
                <td className="py-2.5 text-gray-500 hidden sm:table-cell">
                  {timeAgo(r.created_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}