// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useRef, useState } from "react";
import { LayoutDashboard, Search } from "lucide-react";
import { getAnalytics, getRuns, getStats, getWorkflowTemplates } from "../api";
import { BASE } from "../api/client";
import AnalyticsCharts from "../components/shared/AnalyticsCharts";
import FilterBar from "../components/shared/FilterBar";
import Pagination from "../components/shared/Pagination";
import StatsBar from "../components/shared/StatsBar";
import TaskRunTable from "../components/runs/TaskRunTable";
import type { AnalyticsSummary, Stats, TaskRun } from "../types";

const PAGE_SIZE = 50;

export default function Dashboard() {
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Stats | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");
  const [workflowNames, setWorkflowNames] = useState<Map<number, string>>(
    new Map(),
  );

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Reset offset when filter changes
  useEffect(() => { setOffset(0); }, [filter]);

  const load = useCallback(async () => {
    const [r, s, templates, a] = await Promise.all([
      getRuns({
        status: filter || undefined,
        search: debouncedSearch || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        limit: PAGE_SIZE,
        offset,
      }),
      getStats(),
      getWorkflowTemplates(),
      getAnalytics(),
    ]);
    setRuns(r.items);
    setTotal(r.total);
    setStats(s);
    setWorkflowNames(new Map(templates.map((t) => [t.id, t.name])));
    setAnalytics(a);
  }, [filter, debouncedSearch, sortBy, sortOrder, offset]);

  // Initial load + SSE
  useEffect(() => {
    load();
  }, [load]);

  // SSE live updates
  const eventSourceRef = useRef<EventSource | null>(null);
  useEffect(() => {
    const es = new EventSource(`${BASE}/runs/stream`);
    eventSourceRef.current = es;
    es.onmessage = () => {
      // Re-fetch on any event
      load();
    };
    es.onerror = () => {
      // On SSE error, fall back to polling
      es.close();
      const interval = setInterval(load, 5000);
      return () => clearInterval(interval);
    };
    return () => es.close();
  }, [load]);

  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(column);
      setSortOrder("desc");
    }
  };

  return (
    <>
      <h1 className="text-xl font-semibold mb-6 flex items-center gap-2">
        <LayoutDashboard className="w-5 h-5 text-blue-400" />
        Dashboard
      </h1>
      <StatsBar stats={stats} />
      <AnalyticsCharts data={analytics} />
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search runs..."
            className="w-full pl-9 pr-3 py-2 bg-gray-900/40 border border-gray-800/60 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 backdrop-blur-sm"
          />
        </div>
      </div>
      <FilterBar value={filter} onChange={setFilter} />
      <TaskRunTable
        runs={runs}
        workflowNames={workflowNames}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSort={handleSort}
      />
      <Pagination
        total={total}
        offset={offset}
        limit={PAGE_SIZE}
        onPageChange={setOffset}
      />
    </>
  );
}