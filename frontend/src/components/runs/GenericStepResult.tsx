// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { Bot, Terminal } from "lucide-react";
import type { StepKind } from "../../types";
import CollapsibleJSON from "../shared/CollapsibleJSON";

interface GenericStepResultProps {
  phaseName: string;
  kind: StepKind;
  data: Record<string, unknown>;
}

/**
 * Render a step's result by kind. Used by RunDetail for the new `bash` and
 * `agent` step kinds; legacy_phase results fall back to CollapsibleJSON so
 * the caller can layer phase-specific panels on top.
 */
export default function GenericStepResult({
  phaseName,
  kind,
  data,
}: GenericStepResultProps) {
  if (kind === "bash") return <BashResult phaseName={phaseName} data={data} />;
  if (kind === "agent") return <AgentResult phaseName={phaseName} data={data} />;
  const title = phaseName.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return <CollapsibleJSON title={`${title} Result`} data={data} />;
}

function BashResult({
  phaseName,
  data,
}: {
  phaseName: string;
  data: Record<string, unknown>;
}) {
  const command = String(data.command ?? "");
  const stdout = String(data.stdout ?? "");
  const stderr = String(data.stderr ?? "");
  const exitCode = typeof data.exit_code === "number" ? data.exit_code : null;
  const skipped = data.skipped === true;
  return (
    <div className="rounded-lg border border-gray-700/60 bg-gray-900/60 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-700/60 bg-gray-800/60">
        <Terminal className="w-4 h-4 text-gray-400" />
        <span className="text-sm font-medium text-gray-200">{phaseName}</span>
        {exitCode !== null && (
          <span
            className={`px-2 py-0.5 text-xs rounded font-mono ${
              exitCode === 0
                ? "bg-green-900/60 text-green-300"
                : skipped
                  ? "bg-yellow-900/60 text-yellow-300"
                  : "bg-red-900/60 text-red-300"
            }`}
          >
            exit {exitCode}
            {skipped && " (skipped)"}
          </span>
        )}
      </div>
      {command && (
        <pre className="px-3 py-2 bg-black/40 text-xs text-blue-300 font-mono overflow-x-auto border-b border-gray-700/40">
          $ {command}
        </pre>
      )}
      {stdout && (
        <pre className="px-3 py-2 text-xs text-gray-200 font-mono whitespace-pre-wrap break-words max-h-96 overflow-y-auto">
          {stdout}
        </pre>
      )}
      {stderr && (
        <pre className="px-3 py-2 text-xs text-red-300 font-mono whitespace-pre-wrap break-words max-h-96 overflow-y-auto border-t border-gray-700/40 bg-red-950/20">
          {stderr}
        </pre>
      )}
      {!stdout && !stderr && (
        <p className="px-3 py-2 text-xs text-gray-500 italic">(no output)</p>
      )}
    </div>
  );
}

function AgentResult({
  phaseName,
  data,
}: {
  phaseName: string;
  data: Record<string, unknown>;
}) {
  const provider = String(data.provider ?? "");
  const role = String(data.role ?? "");
  const mode = String(data.mode ?? "");
  const response = data.response;
  const sessionId = data.session_id ? String(data.session_id) : null;
  return (
    <div className="rounded-lg border border-gray-700/60 bg-gray-900/60 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-700/60 bg-gray-800/60 flex-wrap">
        <Bot className="w-4 h-4 text-gray-400" />
        <span className="text-sm font-medium text-gray-200">{phaseName}</span>
        {provider && (
          <span className="px-2 py-0.5 text-xs rounded bg-blue-900/60 text-blue-300 font-mono">
            {provider}
          </span>
        )}
        {role && (
          <span className="px-2 py-0.5 text-xs rounded bg-gray-800 text-gray-300">
            role: {role}
          </span>
        )}
        {mode && (
          <span className="px-2 py-0.5 text-xs rounded bg-gray-800 text-gray-300">
            mode: {mode}
          </span>
        )}
        {sessionId && (
          <span
            className="px-2 py-0.5 text-xs rounded bg-gray-800 text-gray-500 font-mono"
            title="Session id"
          >
            {sessionId.slice(0, 8)}…
          </span>
        )}
      </div>
      {typeof response === "string" ? (
        <pre className="px-3 py-2 text-xs text-gray-200 font-mono whitespace-pre-wrap break-words max-h-96 overflow-y-auto">
          {response}
        </pre>
      ) : response && typeof response === "object" ? (
        <CollapsibleJSON title="Response" data={response as Record<string, unknown>} />
      ) : (
        <p className="px-3 py-2 text-xs text-gray-500 italic">(no response)</p>
      )}
    </div>
  );
}
