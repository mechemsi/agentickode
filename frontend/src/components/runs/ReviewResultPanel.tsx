// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  History,
  Lightbulb,
  ShieldAlert,
  Wrench,
  XCircle,
} from "lucide-react";

interface ReviewIssue {
  severity?: string;
  file?: string;
  line?: number;
  description?: string;
}

interface ReviewIteration {
  attempt: number;
  approved: boolean;
  issues: ReviewIssue[];
  critical_count: number;
  fix_applied: boolean;
  fix_instruction?: string;
  issues_fixed_count?: number;
  issues_remaining_count?: number;
  timestamp?: string;
}

interface ReviewResult {
  approved?: boolean;
  issues?: ReviewIssue[];
  suggestions?: string[];
  strictness?: string;
  iterations?: ReviewIteration[];
}

const severityStyles: Record<string, string> = {
  critical: "bg-red-900/50 text-red-300 border-red-700",
  major: "bg-orange-900/50 text-orange-300 border-orange-700",
  minor: "bg-yellow-900/50 text-yellow-300 border-yellow-700",
};

export default function ReviewResultPanel({ data }: { data: ReviewResult }) {
  const approved = data.approved ?? false;
  const issues = data.issues ?? [];
  const suggestions = data.suggestions ?? [];
  const iterations = data.iterations ?? [];
  const [historyOpen, setHistoryOpen] = useState(false);

  return (
    <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 mb-4 backdrop-blur-sm">
      {/* Approval status */}
      <div className="flex items-center gap-2 mb-4">
        {approved ? (
          <CheckCircle className="w-5 h-5 text-green-400" />
        ) : (
          <XCircle className="w-5 h-5 text-red-400" />
        )}
        <span
          className={`text-sm font-semibold ${approved ? "text-green-300" : "text-red-300"}`}
        >
          {approved ? "Approved" : "Changes Requested"}
        </span>
        {data.strictness && (
          <span className="text-xs text-gray-500 ml-2">
            ({data.strictness})
          </span>
        )}
      </div>

      {/* Issues */}
      {issues.length > 0 && (
        <div className="mb-4">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5" />
            Issues ({issues.length})
          </h4>
          <div className="space-y-1.5">
            {issues.map((issue, i) => {
              const sev = issue.severity ?? "minor";
              const cls = severityStyles[sev] ?? severityStyles.minor;
              return (
                <div
                  key={i}
                  className="flex items-start gap-2 text-sm rounded-lg border border-gray-800/60 bg-gray-950/40 px-3 py-2"
                >
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-gray-400" />
                  <div className="min-w-0 flex-1">
                    <span
                      className={`inline-flex items-center px-1.5 py-0 text-xs rounded border mr-2 ${cls}`}
                    >
                      {sev}
                    </span>
                    {issue.file && (
                      <span className="text-gray-400 text-xs font-mono mr-2">
                        {issue.file}
                        {issue.line ? `:${issue.line}` : ""}
                      </span>
                    )}
                    <span className="text-gray-300">{issue.description}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="mb-4">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Lightbulb className="w-3.5 h-3.5" />
            Suggestions ({suggestions.length})
          </h4>
          <ol className="space-y-1 list-decimal list-inside text-sm text-gray-300">
            {suggestions.map((s, i) => (
              <li key={i} className="pl-1">
                {s}
              </li>
            ))}
          </ol>
        </div>
      )}

      {issues.length === 0 && suggestions.length === 0 && (
        <p className="text-sm text-gray-500 mb-4">
          No issues or suggestions.
        </p>
      )}

      {/* Iteration history (only when multiple iterations) */}
      {iterations.length > 1 && (
        <div className="border-t border-gray-800/60 pt-3">
          <button
            onClick={() => setHistoryOpen(!historyOpen)}
            className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:text-gray-300 transition-colors"
          >
            {historyOpen ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
            <History className="w-3.5 h-3.5" />
            Review History ({iterations.length} iterations)
          </button>
          {historyOpen && (
            <div className="mt-2 space-y-2">
              {iterations.map((iter) => (
                <div
                  key={iter.attempt}
                  className="flex items-center gap-2 text-xs bg-gray-950/40 border border-gray-800/60 rounded-lg px-3 py-2"
                >
                  <span className="text-gray-500 font-mono w-6">
                    #{iter.attempt}
                  </span>
                  {iter.approved ? (
                    <CheckCircle className="w-3.5 h-3.5 text-green-400" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-red-400" />
                  )}
                  <span
                    className={
                      iter.approved ? "text-green-300" : "text-red-300"
                    }
                  >
                    {iter.approved ? "Approved" : "Rejected"}
                  </span>
                  <span className="text-gray-500">
                    {iter.issues.length} issues ({iter.critical_count} critical)
                  </span>
                  {iter.fix_applied && (
                    <span className="inline-flex items-center gap-1 text-blue-400">
                      <Wrench className="w-3 h-3" />
                      Fix Applied
                    </span>
                  )}
                  {iter.issues_fixed_count != null &&
                    iter.issues_fixed_count > 0 && (
                      <span className="text-green-400">
                        {iter.issues_fixed_count} fixed
                      </span>
                    )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}