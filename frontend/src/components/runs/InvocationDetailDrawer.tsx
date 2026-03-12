// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X, Bot, ChevronDown, ChevronRight, Copy, Check, Loader2 } from "lucide-react";
import { getInvocationDetail } from "../../api";
import type { AgentInvocationDetail } from "../../types";

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "-";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      className="p-1 rounded hover:bg-gray-700/50 text-gray-500 hover:text-gray-300 transition-colors"
      title="Copy to clipboard"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

function CollapsibleSection({
  title,
  charCount,
  children,
  defaultOpen = false,
}: {
  title: string;
  charCount?: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-gray-700/50 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-gray-800/30 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
        )}
        <span className="text-sm font-medium text-gray-200">{title}</span>
        {charCount != null && (
          <span className="text-xs text-gray-500 ml-auto">{charCount.toLocaleString()} chars</span>
        )}
      </button>
      {open && <div className="border-t border-gray-700/50">{children}</div>}
    </div>
  );
}

function statusColor(status: string): string {
  switch (status) {
    case "success": return "text-green-400 bg-green-900/30 border-green-700/50";
    case "failed": return "text-red-400 bg-red-900/30 border-red-700/50";
    case "running": return "text-blue-400 bg-blue-900/30 border-blue-700/50";
    case "timeout": return "text-orange-400 bg-orange-900/30 border-orange-700/50";
    default: return "text-gray-400 bg-gray-800/30 border-gray-700/50";
  }
}

interface Props {
  runId: number;
  invocationId: number;
  onClose: () => void;
}

export default function InvocationDetailDrawer({ runId, invocationId, onClose }: Props) {
  const [detail, setDetail] = useState<AgentInvocationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getInvocationDetail(runId, invocationId)
      .then((data) => {
        if (active) setDetail(data as AgentInvocationDetail);
      })
      .catch(() => {
        if (active) setError("Failed to load invocation details");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [runId, invocationId]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return createPortal(
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/60 z-[100]" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-4 sm:inset-8 lg:inset-12 bg-gray-900 border border-gray-700/50 rounded-xl z-[101] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700/50 flex-shrink-0 rounded-t-xl">
          <Bot className="w-5 h-5 text-blue-400" />
          <div className="flex-1 min-w-0">
            {detail ? (
              <>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-sm text-blue-300">{detail.agent_name}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700/60 text-gray-300">
                    {detail.phase_name ?? "-"}
                  </span>
                  <span className={`text-xs px-1.5 py-0.5 rounded border ${statusColor(detail.status)}`}>
                    {detail.status}
                  </span>
                  {detail.exit_code !== null && (
                    <span className="text-xs text-gray-500">exit {detail.exit_code}</span>
                  )}
                </div>
                <p className="text-sm text-gray-400 truncate mt-0.5">
                  {detail.subtask_title || "—"}
                </p>
              </>
            ) : (
              <span className="text-sm text-gray-400">Invocation #{invocationId}</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {loading && (
            <div className="flex items-center gap-2 text-gray-500 text-sm py-8 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading invocation details...
            </div>
          )}

          {error && <p className="text-red-400 text-sm">{error}</p>}

          {detail && !loading && (
            <>
              {/* Meta bar */}
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-400">
                <span>Duration: {formatDuration(detail.duration_seconds)}</span>
                {detail.started_at && (
                  <span>Started: {new Date(detail.started_at).toLocaleString()}</span>
                )}
                {detail.completed_at && (
                  <span>Completed: {new Date(detail.completed_at).toLocaleString()}</span>
                )}
                <span>Prompt: {detail.prompt_chars.toLocaleString()} chars</span>
                <span>Response: {detail.response_chars.toLocaleString()} chars</span>
                {detail.estimated_tokens_in != null && (
                  <span>
                    Tokens: {detail.estimated_tokens_in.toLocaleString()} in / {detail.estimated_tokens_out?.toLocaleString() ?? 0} out
                    {detail.metadata_?.token_source === "api" ? (
                      <span className="ml-1 text-[10px] px-1 py-0.5 rounded bg-green-900/40 text-green-400">(actual)</span>
                    ) : (
                      <span className="ml-1 text-[10px] px-1 py-0.5 rounded bg-gray-700/40 text-gray-500">(est.)</span>
                    )}
                  </span>
                )}
                {detail.estimated_cost_usd != null && (
                  <span className="text-amber-400">Cost: ${detail.estimated_cost_usd.toFixed(4)}</span>
                )}
              </div>

              {/* Session ID */}
              {detail.session_id && (
                <div className="flex items-center gap-2 px-3 py-2 bg-purple-900/20 border border-purple-700/30 rounded-lg">
                  <span className="text-xs text-purple-300 font-medium">Session:</span>
                  <code className="text-xs text-purple-200 font-mono flex-1">{detail.session_id}</code>
                  <CopyButton text={detail.session_id} />
                </div>
              )}

              {/* System Prompt */}
              {detail.system_prompt_text && (
                <CollapsibleSection title="System Prompt" charCount={detail.system_prompt_text.length}>
                  <div className="relative">
                    <div className="absolute top-2 right-2">
                      <CopyButton text={detail.system_prompt_text} />
                    </div>
                    <pre className="text-xs text-gray-300 bg-gray-950/50 p-4 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto">
                      {detail.system_prompt_text}
                    </pre>
                  </div>
                </CollapsibleSection>
              )}

              {/* Prompt */}
              {detail.prompt_text && (
                <CollapsibleSection title="Prompt" charCount={detail.prompt_text.length} defaultOpen>
                  <div className="relative">
                    <div className="absolute top-2 right-2">
                      <CopyButton text={detail.prompt_text} />
                    </div>
                    <pre className="text-xs text-gray-300 bg-gray-950/50 p-4 overflow-x-auto whitespace-pre-wrap max-h-[32rem] overflow-y-auto">
                      {detail.prompt_text}
                    </pre>
                  </div>
                </CollapsibleSection>
              )}

              {/* Response */}
              {detail.response_text && (
                <CollapsibleSection title="Response" charCount={detail.response_text.length} defaultOpen>
                  <div className="relative">
                    <div className="absolute top-2 right-2">
                      <CopyButton text={detail.response_text} />
                    </div>
                    <pre className="text-xs text-gray-300 bg-gray-950/50 p-4 overflow-x-auto whitespace-pre-wrap max-h-[32rem] overflow-y-auto">
                      {detail.response_text}
                    </pre>
                  </div>
                </CollapsibleSection>
              )}

              {/* Error */}
              {detail.error_message && (
                <CollapsibleSection title="Error" defaultOpen>
                  <pre className="text-xs text-red-300 bg-red-950/30 p-4 overflow-x-auto whitespace-pre-wrap">
                    {detail.error_message}
                  </pre>
                </CollapsibleSection>
              )}

              {/* Files Changed */}
              {detail.files_changed && detail.files_changed.length > 0 && (
                <CollapsibleSection title={`Files Changed (${detail.files_changed.length})`}>
                  <div className="p-3 space-y-1">
                    {detail.files_changed.map((f) => (
                      <div key={f} className="text-xs font-mono text-gray-300 px-2 py-1 bg-gray-800/50 rounded">
                        {f}
                      </div>
                    ))}
                  </div>
                </CollapsibleSection>
              )}

              {/* Metadata */}
              {detail.metadata_ && Object.keys(detail.metadata_).length > 0 && (
                <CollapsibleSection title="Metadata">
                  <pre className="text-xs text-gray-400 bg-gray-950/50 p-4 overflow-x-auto">
                    {JSON.stringify(detail.metadata_, null, 2)}
                  </pre>
                </CollapsibleSection>
              )}
            </>
          )}
        </div>
      </div>
    </>,
    document.body,
  );
}