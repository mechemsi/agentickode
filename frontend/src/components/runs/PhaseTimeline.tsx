// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import {
  Brain,
  CheckCircle2,
  Clock,
  Code,
  Eye,
  FileText,
  FolderOpen,
  Loader2,
  Pause,
  Play,
  Rocket,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { ElementType } from "react";
import type { PhaseExecution } from "../../types";
import { formatDuration } from "../../utils/formatDuration";

const PHASES = [
  "workspace_setup",
  "init",
  "planning",
  "coding",
  "reviewing",
  "approval",
  "finalization",
];

const phaseIcons: Record<string, ElementType> = {
  workspace_setup: FolderOpen,
  init: FileText,
  planning: Brain,
  coding: Code,
  reviewing: Eye,
  approval: ShieldCheck,
  finalization: Rocket,
};

function phaseLabel(p: string): string {
  return p
    .replace("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}


const statusStyles: Record<string, string> = {
  completed: "bg-green-900/60 text-green-300",
  running: "bg-blue-900/60 text-blue-300 ring-1 ring-blue-500",
  waiting: "bg-yellow-900/60 text-yellow-300 ring-1 ring-yellow-500",
  failed: "bg-red-900/60 text-red-300 ring-1 ring-red-500",
  skipped: "bg-gray-800/60 text-gray-500 line-through",
  pending: "bg-gray-800 text-gray-500",
};

const statusIcon: Record<string, ElementType> = {
  completed: CheckCircle2,
  running: Loader2,
  waiting: Pause,
  failed: XCircle,
  pending: Clock,
};

interface PhaseTimelineProps {
  phases?: PhaseExecution[];
  currentPhase?: string | null;
  status?: string;
  onAdvance?: (phaseName: string) => void;
  selectedPhase?: string | null;
  onPhaseClick?: (phaseName: string | null) => void;
}

export default function PhaseTimeline({
  phases,
  currentPhase,
  status,
  onAdvance,
  selectedPhase,
  onPhaseClick,
}: PhaseTimelineProps) {
  // If we have PhaseExecution data, use the rich view
  if (phases && phases.length > 0) {
    return (
      <div className="flex flex-wrap gap-1 items-center">
        {onPhaseClick && (
          <button
            onClick={() => onPhaseClick(null)}
            className={`px-2 py-1 text-xs rounded inline-flex items-center gap-1 cursor-pointer transition-all ${
              selectedPhase === undefined || selectedPhase === null
                ? "bg-blue-900/60 text-blue-300 ring-2 ring-blue-400"
                : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            All Logs
          </button>
        )}
        {onPhaseClick && (
          <span className="text-gray-700 text-xs">&rarr;</span>
        )}
        {phases.map((pe, i) => {
          const cls = statusStyles[pe.status] || statusStyles.pending;
          const PhaseIcon = phaseIcons[pe.phase_name];
          const StatusIcon = statusIcon[pe.status];
          const isWaiting = pe.status === "waiting";
          const canAdvance = isWaiting && pe.trigger_mode === "wait_for_trigger";
          const isApprovalWait = isWaiting && pe.trigger_mode === "wait_for_approval";
          const isSelected = selectedPhase === pe.phase_name;
          const isRunning = pe.status === "running";
          const duration = formatDuration(pe.started_at, pe.completed_at);

          return (
            <div key={pe.id} className="flex items-center gap-1">
              <span
                onClick={() => onPhaseClick?.(pe.phase_name)}
                className={`px-2 py-1 text-xs rounded inline-flex items-center gap-1 ${cls} ${
                  onPhaseClick ? "cursor-pointer hover:brightness-125 transition-all" : ""
                } ${isSelected ? "ring-2 ring-blue-400" : ""}`}
                role={onPhaseClick ? "button" : undefined}
                tabIndex={onPhaseClick ? 0 : undefined}
              >
                {StatusIcon && (
                  <StatusIcon className={`w-3 h-3 ${isRunning ? "animate-spin" : ""}`} />
                )}
                {PhaseIcon && <PhaseIcon className="w-3 h-3" />}
                {phaseLabel(pe.phase_name)}
                {duration !== null && (
                  <span className="text-[10px] opacity-70">
                    ({duration}{isRunning ? "..." : ""})
                  </span>
                )}
                {pe.retry_count > 0 && (
                  <span className="text-[10px] opacity-70">({pe.retry_count}x)</span>
                )}
              </span>
              {canAdvance && onAdvance && (
                <button
                  onClick={() => onAdvance(pe.phase_name)}
                  className="px-1.5 py-0.5 text-[10px] bg-yellow-600 hover:bg-yellow-500 text-white rounded inline-flex items-center gap-0.5"
                  title="Advance this phase"
                >
                  <Play className="w-2.5 h-2.5" />
                  Advance
                </button>
              )}
              {isApprovalWait && (
                <span className="px-1.5 py-0.5 text-[10px] bg-orange-900/50 text-orange-300 rounded">
                  Awaiting Approval
                </span>
              )}
              {i < phases.length - 1 && (
                <span className="text-gray-700 text-xs">&rarr;</span>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // Fallback: old-style display using currentPhase/status
  const currentIdx = currentPhase ? PHASES.indexOf(currentPhase) : -1;
  const done = status === "completed";

  return (
    <div className="flex flex-wrap gap-1 items-center">
      {PHASES.map((p, i) => {
        let cls = "bg-gray-800 text-gray-500";
        if (done || i < currentIdx) cls = "bg-green-900/60 text-green-300";
        else if (i === currentIdx)
          cls = "bg-blue-900/60 text-blue-300 ring-1 ring-blue-500";

        const Icon = phaseIcons[p];

        return (
          <div key={p} className="flex items-center gap-1">
            <span className={`px-2 py-1 text-xs rounded inline-flex items-center gap-1 ${cls}`}>
              {Icon && <Icon className="w-3 h-3" />}
              {phaseLabel(p)}
            </span>
            {i < PHASES.length - 1 && (
              <span className="text-gray-700 text-xs">&rarr;</span>
            )}
          </div>
        );
      })}
    </div>
  );
}