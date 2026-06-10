// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import {
  Code,
  FileText,
  FolderOpen,
  Rocket,
} from "lucide-react";
import type { ElementType } from "react";

// Icon hints for the well-known flow phase names.
const phaseIcons: Record<string, ElementType> = {
  workspace_setup: FolderOpen,
  init: FileText,
  agent: Code,
  finalization: Rocket,
};

function phaseLabel(p: string): string {
  return p
    .replace("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

interface PhaseTimelineProps {
  currentPhase?: string | null;
  status?: string;
}

export default function PhaseTimeline({ currentPhase, status }: PhaseTimelineProps) {
  // ADR-009: a run is a single agent call, so there's no per-step timeline —
  // just surface the current step (or a terminal status).
  if (!currentPhase) {
    return (
      <div className="flex flex-wrap gap-1 items-center">
        <span className="px-2 py-1 text-xs rounded bg-gray-800 text-gray-500">
          {status === "completed" ? "Completed" : "Pending"}
        </span>
      </div>
    );
  }

  const FallbackIcon = phaseIcons[currentPhase];
  const fallbackCls =
    status === "completed"
      ? "bg-green-900/60 text-green-300"
      : "bg-blue-900/60 text-blue-300 ring-1 ring-blue-500";

  return (
    <div className="flex flex-wrap gap-1 items-center">
      <span className={`px-2 py-1 text-xs rounded inline-flex items-center gap-1 ${fallbackCls}`}>
        {FallbackIcon && <FallbackIcon className="w-3 h-3" />}
        {phaseLabel(currentPhase)}
      </span>
    </div>
  );
}
