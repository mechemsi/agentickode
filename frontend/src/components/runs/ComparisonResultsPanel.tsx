// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { CheckCircle, FileCode, GitBranch, Trophy, XCircle } from "lucide-react";
import { pickComparisonWinner } from "../../api";
import type { ComparisonResults } from "../../types";

interface Props {
  runId: number;
  comparison: ComparisonResults;
  onWinnerPicked: () => void;
}

export default function ComparisonResultsPanel({ runId, comparison, onWinnerPicked }: Props) {
  const [picking, setPicking] = useState<string | null>(null);

  const handlePick = async (label: "a" | "b") => {
    setPicking(label);
    try {
      await pickComparisonWinner(runId, label);
      onWinnerPicked();
    } finally {
      setPicking(null);
    }
  };

  return (
    <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 mb-4 backdrop-blur-sm">
      <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2 mb-1">
        <GitBranch className="w-4 h-4 text-gray-400" />
        A/B Comparison Results
      </h3>
      <p className="text-xs text-gray-500 mb-4">
        Base commit: <code className="text-gray-400">{comparison.base_commit.slice(0, 8)}</code>
        {comparison.winner && (
          <span className="ml-2 text-green-400">
            Winner: Agent {comparison.winner.toUpperCase()}
          </span>
        )}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {(["a", "b"] as const).map((label) => {
          const agent = comparison.agents[label];
          const isWinner = comparison.winner === label;

          return (
            <div
              key={label}
              className={`rounded-lg border p-4 ${
                isWinner
                  ? "border-green-600 bg-green-950/20"
                  : "border-gray-800/60 bg-gray-950/40"
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold uppercase text-gray-500">
                    Agent {label.toUpperCase()}
                  </span>
                  <span className="text-sm font-medium text-gray-200">
                    {agent.agent_name}
                  </span>
                  {isWinner && <Trophy className="w-4 h-4 text-yellow-400" />}
                </div>
              </div>

              {/* Stats */}
              <div className="flex gap-4 text-xs text-gray-400 mb-3">
                {agent.total_duration_seconds != null && (
                  <span>{agent.total_duration_seconds.toFixed(0)}s</span>
                )}
                {agent.total_cost_usd != null && (
                  <span>${agent.total_cost_usd.toFixed(4)}</span>
                )}
              </div>

              {/* Subtask results */}
              <div className="space-y-1.5">
                {agent.results.map((r, i) => {
                  const ok = r.exit_code === 0;
                  return (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      {ok ? (
                        <CheckCircle className="w-3.5 h-3.5 text-green-400 mt-0.5 shrink-0" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 shrink-0" />
                      )}
                      <div className="min-w-0 flex-1">
                        <span className="text-gray-300 text-xs">
                          {r.subtask_title}
                        </span>
                        {r.files_changed.length > 0 && (
                          <div className="mt-0.5 flex flex-wrap gap-1">
                            {r.files_changed.map((f) => (
                              <span
                                key={f}
                                className="inline-flex items-center gap-0.5 text-[10px] text-gray-500 bg-gray-800/60 rounded px-1 py-0.5"
                              >
                                <FileCode className="w-2.5 h-2.5" />
                                {f}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Branch info */}
              <p className="text-[10px] text-gray-600 mt-2">
                Branch: {agent.branch}
              </p>

              {/* Pick winner button */}
              {!comparison.winner && (
                <button
                  onClick={() => handlePick(label)}
                  disabled={picking !== null}
                  className="mt-3 w-full px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-xs rounded-lg transition-colors"
                >
                  {picking === label ? "Picking..." : `Pick Agent ${label.toUpperCase()}`}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}