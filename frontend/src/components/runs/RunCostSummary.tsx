// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, DollarSign } from "lucide-react";
import { getRunInvocations } from "../../api";
import type { AgentInvocation } from "../../types";

interface PhaseSummary {
  phase: string;
  tokensIn: number;
  tokensOut: number;
  cost: number;
  duration: number;
  count: number;
  hasActual: boolean;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function TokenSourceBadge({ hasActual }: { hasActual: boolean }) {
  if (hasActual) {
    return (
      <span className="text-[10px] px-1 py-0.5 rounded bg-green-900/40 text-green-400 font-medium">
        actual
      </span>
    );
  }
  return (
    <span className="text-[10px] px-1 py-0.5 rounded bg-gray-700/40 text-gray-500 font-medium">
      est.
    </span>
  );
}

interface Props {
  runId: number;
}

export default function RunCostSummary({ runId }: Props) {
  const [invocations, setInvocations] = useState<AgentInvocation[]>([]);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    let active = true;
    getRunInvocations(runId)
      .then((data) => { if (active) setInvocations(data); })
      .catch(() => {});
    return () => { active = false; };
  }, [runId]);

  if (invocations.length === 0) return null;

  // Aggregate totals
  const totals = invocations.reduce(
    (acc, inv) => ({
      tokensIn: acc.tokensIn + (inv.estimated_tokens_in ?? 0),
      tokensOut: acc.tokensOut + (inv.estimated_tokens_out ?? 0),
      cost: acc.cost + (inv.estimated_cost_usd ?? 0),
      duration: acc.duration + (inv.duration_seconds ?? 0),
    }),
    { tokensIn: 0, tokensOut: 0, cost: 0, duration: 0 },
  );

  // Per-phase breakdown
  const phaseMap = new Map<string, PhaseSummary>();
  for (const inv of invocations) {
    const phase = inv.phase_name ?? "unknown";
    const existing = phaseMap.get(phase);
    const tokenSource = (inv.metadata_?.token_source as string) ?? "";
    const hasActual = tokenSource === "api";

    if (existing) {
      existing.tokensIn += inv.estimated_tokens_in ?? 0;
      existing.tokensOut += inv.estimated_tokens_out ?? 0;
      existing.cost += inv.estimated_cost_usd ?? 0;
      existing.duration += inv.duration_seconds ?? 0;
      existing.count += 1;
      if (hasActual) existing.hasActual = true;
    } else {
      phaseMap.set(phase, {
        phase,
        tokensIn: inv.estimated_tokens_in ?? 0,
        tokensOut: inv.estimated_tokens_out ?? 0,
        cost: inv.estimated_cost_usd ?? 0,
        duration: inv.duration_seconds ?? 0,
        count: 1,
        hasActual,
      });
    }
  }

  const phases = Array.from(phaseMap.values());
  const anyActual = phases.some((p) => p.hasActual);

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-5 mb-6 backdrop-blur-sm">
      <button
        className="w-full flex items-center gap-2 text-left mb-3"
        onClick={() => setCollapsed((v) => !v)}
      >
        <DollarSign className="w-4 h-4 text-amber-400 flex-shrink-0" />
        <h2 className="text-lg font-semibold flex-1">Cost Summary</h2>
        <span className="text-sm text-amber-400 mr-2">${totals.cost.toFixed(4)}</span>
        <span className="text-xs text-gray-500 mr-2">
          {totals.tokensIn.toLocaleString()} in / {totals.tokensOut.toLocaleString()} out
        </span>
        {collapsed ? (
          <ChevronRight className="w-4 h-4 text-gray-500" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-500" />
        )}
      </button>

      {!collapsed && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <div className="bg-gray-800/40 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Total Cost</p>
              <p className="text-lg font-semibold text-amber-400">${totals.cost.toFixed(4)}</p>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Tokens In</p>
              <p className="text-lg font-semibold text-gray-200">{totals.tokensIn.toLocaleString()}</p>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Tokens Out</p>
              <p className="text-lg font-semibold text-gray-200">{totals.tokensOut.toLocaleString()}</p>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Total Duration</p>
              <p className="text-lg font-semibold text-gray-200">{formatDuration(totals.duration)}</p>
            </div>
          </div>

          {/* Per-phase table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 border-b border-gray-700/50">
                  <th className="text-left py-2 pr-4">Phase</th>
                  <th className="text-right py-2 px-2">Invocations</th>
                  <th className="text-right py-2 px-2">Tokens In</th>
                  <th className="text-right py-2 px-2">Tokens Out</th>
                  <th className="text-right py-2 px-2">Cost</th>
                  <th className="text-right py-2 px-2">Duration</th>
                  {anyActual && <th className="text-right py-2 pl-2">Source</th>}
                </tr>
              </thead>
              <tbody>
                {phases.map((p) => (
                  <tr key={p.phase} className="border-b border-gray-800/30">
                    <td className="py-2 pr-4 text-gray-200 capitalize">{p.phase}</td>
                    <td className="py-2 px-2 text-right text-gray-400">{p.count}</td>
                    <td className="py-2 px-2 text-right text-gray-300">{p.tokensIn.toLocaleString()}</td>
                    <td className="py-2 px-2 text-right text-gray-300">{p.tokensOut.toLocaleString()}</td>
                    <td className="py-2 px-2 text-right text-amber-400">${p.cost.toFixed(4)}</td>
                    <td className="py-2 px-2 text-right text-gray-400">{formatDuration(p.duration)}</td>
                    {anyActual && (
                      <td className="py-2 pl-2 text-right">
                        <TokenSourceBadge hasActual={p.hasActual} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}