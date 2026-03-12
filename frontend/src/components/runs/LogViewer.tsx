// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useRef, useState } from "react";
import { Bug } from "lucide-react";
import { getRunLogs } from "../../api";
import type { TaskLog } from "../../types";
import LogEntryMetadata from "./LogEntryMetadata";

const levelColors: Record<string, string> = {
  info: "text-gray-300",
  warning: "text-yellow-400",
  error: "text-red-400",
  debug: "text-gray-500",
};

const levelIcons: Record<string, string> = {
  info: "\u2022",
  warning: "\u26a0",
  error: "\u2716",
  debug: "\u2023",
};

interface LogViewerProps {
  runId: number;
  phase?: string | null;
}

export default function LogViewer({ runId, phase }: LogViewerProps) {
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [historicalLogs, setHistoricalLogs] = useState<TaskLog[]>([]);
  const [showDebug, setShowDebug] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Fetch historical logs when a specific phase is selected
  useEffect(() => {
    if (!phase) {
      setHistoricalLogs([]);
      return;
    }
    let cancelled = false;
    getRunLogs(runId, { phase }).then((data) => {
      if (!cancelled) setHistoricalLogs(data);
    });
    return () => { cancelled = true; };
  }, [runId, phase]);

  // Reset live logs when phase filter changes
  useEffect(() => {
    setLogs([]);
  }, [phase]);

  // WebSocket for live logs
  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/runs/${runId}/logs`);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as TaskLog;
      if (phase && msg.phase !== phase) return;
      setLogs((prev) => [...prev, msg]);
    };
    return () => ws.close();
  }, [runId, phase]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [logs, historicalLogs]);

  const allLogs = phase ? [...historicalLogs, ...logs] : logs;
  const displayLogs = showDebug ? allLogs : allLogs.filter((l) => l.level !== "debug");
  const debugCount = allLogs.filter((l) => l.level === "debug").length;

  const emptyText = phase
    ? `No logs for ${phase.replace("_", " ")}`
    : "Waiting for logs...";

  return (
    <div>
      {/* Toolbar */}
      {debugCount > 0 && (
        <div className="flex items-center justify-end mb-2">
          <button
            onClick={() => setShowDebug(!showDebug)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors ${
              showDebug
                ? "bg-gray-700 text-gray-200"
                : "bg-gray-800/50 text-gray-500 hover:text-gray-400"
            }`}
          >
            <Bug className="w-3 h-3" />
            {showDebug ? "Hide" : "Show"} debug ({debugCount})
          </button>
        </div>
      )}

      {/* Log area */}
      <div className="bg-gray-900 rounded border border-gray-800 p-4 max-h-[32rem] overflow-y-auto font-mono text-xs">
        {displayLogs.length === 0 && (
          <p className="text-gray-600 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-gray-600 animate-pulse-slow" />
            {emptyText}
          </p>
        )}
        {displayLogs.map((l, i) => (
          <div key={l.id ?? `live-${i}`}>
            <div
              className={`flex gap-2 leading-5 ${l.level === "debug" ? "opacity-60" : ""}`}
            >
              <span className="text-gray-600 shrink-0 tabular-nums">
                {new Date(l.timestamp).toLocaleTimeString()}
              </span>
              <span
                className={`shrink-0 w-3 text-center ${levelColors[l.level] ?? "text-gray-300"}`}
                title={l.level}
              >
                {levelIcons[l.level] ?? "\u2022"}
              </span>
              {!phase && l.phase && (
                <span className="text-gray-600 shrink-0 w-20 truncate" title={l.phase}>
                  {l.phase}
                </span>
              )}
              <span className={`${levelColors[l.level] ?? "text-gray-300"} whitespace-pre-wrap break-all`}>
                {l.message}
              </span>
            </div>
            {l.metadata_ && <LogEntryMetadata metadata={l.metadata_} />}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}