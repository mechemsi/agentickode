// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { Activity, Clock, DollarSign, TrendingUp } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AnalyticsSummary } from "../../types";

function MetricCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4 flex items-center gap-3">
      <div className="text-blue-400">{icon}</div>
      <div>
        <div className="text-xs text-gray-400 uppercase tracking-wider">
          {label}
        </div>
        <div className="text-lg font-semibold text-gray-100">{value}</div>
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

const tooltipStyle = {
  backgroundColor: "#1f2937",
  border: "1px solid #374151",
  borderRadius: "8px",
  fontSize: 12,
};

export default function AnalyticsCharts({
  data,
}: {
  data: AnalyticsSummary | null;
}) {
  if (!data) return null;

  const phaseData = data.avg_phase_durations.map((p) => ({
    name: p.phase_name,
    seconds: p.avg_seconds,
  }));

  const agentData = data.agent_stats.map((a) => ({
    name: a.agent_name,
    runs: a.total_runs,
    success: a.success_rate,
  }));

  const trendData = data.runs_over_time.map((d) => ({
    date: d.date.slice(5), // MM-DD
    count: d.count,
  }));

  const costData = (data.cost_stats?.cost_by_agent ?? []).map((c) => ({
    name: c.agent_name,
    cost: c.cost_usd,
  }));

  return (
    <div className="mb-6 space-y-4">
      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Success Rate"
          value={`${data.success_rate}%`}
          icon={<TrendingUp className="w-5 h-5" />}
        />
        <MetricCard
          label="Avg Duration"
          value={formatDuration(data.avg_duration_seconds)}
          icon={<Clock className="w-5 h-5" />}
        />
        <MetricCard
          label="Total Runs"
          value={String(data.total_runs)}
          icon={<Activity className="w-5 h-5" />}
        />
        <MetricCard
          label="Est. Total Cost"
          value={
            data.cost_stats
              ? `$${data.cost_stats.total_cost_usd.toFixed(2)}`
              : "N/A"
          }
          icon={<DollarSign className="w-5 h-5" />}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Phase durations */}
        {phaseData.length > 0 && (
          <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Avg Phase Duration (s)
            </h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={phaseData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "#9ca3af" }}
                />
                <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="seconds" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Agent comparison */}
        {agentData.length > 0 && (
          <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Agent Runs
            </h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={agentData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "#9ca3af" }}
                />
                <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="runs" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Runs trend */}
        {trendData.length > 0 && (
          <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Daily Runs (14d)
            </h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: "#9ca3af" }}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "#9ca3af" }}
                  allowDecimals={false}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Cost by agent */}
        {costData.length > 0 && (
          <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Cost by Agent ($)
            </h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={costData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "#9ca3af" }}
                />
                <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="cost" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}