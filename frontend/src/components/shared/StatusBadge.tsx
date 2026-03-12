// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import {
  Ban,
  CheckCircle,
  Clock,
  Play,
  ShieldCheck,
  Timer,
  XCircle,
} from "lucide-react";
import type { ElementType } from "react";

const colors: Record<string, string> = {
  pending: "bg-yellow-900/50 text-yellow-300 border-yellow-700",
  running: "bg-blue-900/50 text-blue-300 border-blue-700",
  awaiting_approval: "bg-purple-900/50 text-purple-300 border-purple-700",
  completed: "bg-green-900/50 text-green-300 border-green-700",
  failed: "bg-red-900/50 text-red-300 border-red-700",
  cancelled: "bg-gray-800 text-gray-400 border-gray-600",
  timeout: "bg-orange-900/50 text-orange-300 border-orange-700",
};

const icons: Record<string, ElementType> = {
  pending: Clock,
  running: Play,
  awaiting_approval: ShieldCheck,
  completed: CheckCircle,
  failed: XCircle,
  cancelled: Ban,
  timeout: Timer,
};

export default function StatusBadge({ status }: { status: string }) {
  const cls = colors[status] ?? "bg-gray-800 text-gray-300 border-gray-600";
  const Icon = icons[status];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded border ${cls}`}>
      {Icon && <Icon className="w-3 h-3" />}
      {status.replace("_", " ")}
    </span>
  );
}