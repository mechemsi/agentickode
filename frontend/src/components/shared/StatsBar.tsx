// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import {
  Activity,
  CheckCircle,
  Clock,
  Play,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { ElementType } from "react";
import type { Stats } from "../../types";

const items: { key: keyof Stats; label: string; color: string; bg: string; icon: ElementType }[] = [
  { key: "total_runs", label: "Total", color: "text-white", bg: "bg-gray-500/5", icon: Activity },
  { key: "pending", label: "Pending", color: "text-yellow-400", bg: "bg-yellow-500/5", icon: Clock },
  { key: "running", label: "Running", color: "text-blue-400", bg: "bg-blue-500/5", icon: Play },
  { key: "awaiting_approval", label: "Awaiting", color: "text-purple-400", bg: "bg-purple-500/5", icon: ShieldCheck },
  { key: "completed", label: "Done", color: "text-green-400", bg: "bg-green-500/5", icon: CheckCircle },
  { key: "failed", label: "Failed", color: "text-red-400", bg: "bg-red-500/5", icon: XCircle },
];

export default function StatsBar({ stats }: { stats: Stats | null }) {
  if (!stats) return null;
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 mb-6">
      {items.map((it) => {
        const Icon = it.icon;
        return (
          <div
            key={it.key}
            className={`text-center ${it.bg} border border-gray-800/60 rounded-xl p-3 shadow-sm backdrop-blur-sm hover:border-gray-700/60 transition-all`}
          >
            <Icon className={`w-4 h-4 mx-auto mb-1.5 ${it.color} opacity-50`} />
            <div className={`text-2xl font-bold ${it.color}`}>
              {stats[it.key]}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">{it.label}</div>
          </div>
        );
      })}
    </div>
  );
}