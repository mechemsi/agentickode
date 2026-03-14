// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { CheckCircle, Code, FileCode, XCircle } from "lucide-react";

interface SubtaskResult {
  subtask_title?: string;
  files_changed?: string[];
  exit_code?: number | string;
  consolidated?: boolean;
  batch_mode?: boolean;
}

interface TestResult {
  success?: boolean;
  output?: string;
  error?: string;
}

interface CodingResults {
  results?: SubtaskResult[];
  test_results?: TestResult | null;
}

export default function CodingResultsPanel({ data }: { data: CodingResults }) {
  const results = data.results ?? [];
  const testResults = data.test_results;

  return (
    <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 mb-4 backdrop-blur-sm">
      <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2 mb-3">
        <Code className="w-4 h-4 text-gray-400" />
        Coding Results
        <span className="text-gray-500 font-normal">
          ({results.length} subtask{results.length !== 1 ? "s" : ""})
        </span>
        {results.some((r) => r.consolidated) && (
          <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-purple-900/50 text-purple-300 border border-purple-700/50">
            Consolidated
          </span>
        )}
        {results.some((r) => r.batch_mode) && !results.some((r) => r.consolidated) && (
          <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-blue-900/50 text-blue-300 border border-blue-700/50">
            Batch
          </span>
        )}
      </h3>

      {results.length === 0 ? (
        <p className="text-sm text-gray-500">No subtask results.</p>
      ) : (
        <div className="space-y-2">
          {results.map((r, i) => {
            const ok = r.exit_code === 0;
            return (
              <div
                key={i}
                className="flex items-start gap-3 rounded-lg border border-gray-800/60 bg-gray-950/40 px-3 py-2 text-sm"
              >
                {ok ? (
                  <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 shrink-0" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <span className="text-gray-200 font-medium">
                    {r.subtask_title ?? `Subtask ${i + 1}`}
                  </span>
                  <span
                    className={`ml-2 inline-flex items-center px-1.5 py-0 text-xs rounded border ${
                      ok
                        ? "bg-green-900/40 text-green-300 border-green-800"
                        : "bg-red-900/40 text-red-300 border-red-800"
                    }`}
                  >
                    exit {String(r.exit_code ?? "?")}
                  </span>
                  {r.files_changed && r.files_changed.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {r.files_changed.map((f) => (
                        <span
                          key={f}
                          className="inline-flex items-center gap-1 text-xs text-gray-400 bg-gray-800/60 rounded px-1.5 py-0.5"
                        >
                          <FileCode className="w-3 h-3" />
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
      )}

      {testResults && (
        <div className="mt-3 pt-3 border-t border-gray-800/60">
          <div className="flex items-center gap-2 text-sm">
            {testResults.success ? (
              <CheckCircle className="w-4 h-4 text-green-400" />
            ) : (
              <XCircle className="w-4 h-4 text-red-400" />
            )}
            <span className={testResults.success ? "text-green-300" : "text-red-300"}>
              Tests {testResults.success ? "passed" : "failed"}
            </span>
          </div>
          {testResults.output && (
            <pre className="mt-1 text-xs text-gray-500 max-h-32 overflow-auto whitespace-pre-wrap">
              {testResults.output}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}