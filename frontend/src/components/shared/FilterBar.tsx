// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { Filter } from "lucide-react";

const statuses = [
  "",
  "pending",
  "running",
  "awaiting_approval",
  "waiting_for_trigger",
  "completed",
  "failed",
  "cancelled",
  "timeout",
];

const statusLabels: Record<string, string> = {
  waiting_for_trigger: "Plan Review",
};

export default function FilterBar({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-5 bg-gray-900/40 border border-gray-800/60 rounded-xl px-4 py-3 backdrop-blur-sm">
      <Filter className="w-4 h-4 text-gray-500" />
      {statuses.map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          className={`px-3 py-1 text-xs rounded-lg border transition-all ${
            value === s
              ? "bg-blue-600/20 border-blue-500/40 text-blue-300 shadow-sm"
              : "border-gray-700/50 text-gray-400 hover:text-white hover:border-gray-500 hover:bg-gray-800/40"
          }`}
        >
          {statusLabels[s] || s || "All"}
        </button>
      ))}
    </div>
  );
}