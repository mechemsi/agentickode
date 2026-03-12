// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2, RefreshCw, RotateCcw, X } from "lucide-react";
import { getAgentStatus, installAgentStream } from "../../api";
import type { AgentInstallStatus, AgentManagementStatus } from "../../types";

function StatusBadge({ installed }: { installed: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${
        installed
          ? "bg-green-500/10 text-green-400 border border-green-800/40"
          : "bg-gray-800/50 text-gray-500 border border-gray-700/40"
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${installed ? "bg-green-400" : "bg-gray-500"}`} />
      {installed ? "Installed" : "Not Installed"}
    </span>
  );
}

interface InstallProgress {
  agentName: string;
  displayName: string;
  status: "installing" | "success" | "error";
  message?: string;
  output?: string;
  error?: string;
}

function InstallDialog({ progress, onClose }: { progress: InstallProgress; onClose: () => void }) {
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [progress.output]);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-5 w-full max-w-lg mx-4 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-white flex items-center gap-2">
            {progress.status === "installing" && (
              <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
            )}
            {progress.status === "installing"
              ? `Installing ${progress.displayName}...`
              : progress.status === "success"
                ? `${progress.displayName} Installed`
                : `${progress.displayName} Install Failed`}
          </h3>
          {progress.status !== "installing" && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1 rounded hover:bg-gray-700/50"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {progress.status === "success" && (
          <div className="text-green-400 text-sm mb-3">
            {progress.message || "Installation completed successfully."}
          </div>
        )}

        {progress.status === "error" && progress.error && (
          <pre className="text-red-400/80 text-xs whitespace-pre-wrap break-all bg-red-950/20 border border-red-900/30 rounded px-3 py-2 max-h-40 overflow-y-auto mb-3">
            {progress.error}
          </pre>
        )}

        <div>
          <span className="text-xs text-gray-500 mb-1 block">
            {progress.status === "installing" ? "Live output:" : "Install output:"}
          </span>
          <div
            ref={outputRef}
            className="text-xs text-gray-400 bg-gray-950/60 border border-gray-800/50 rounded px-3 py-2 max-h-72 overflow-y-auto whitespace-pre-wrap break-all font-mono"
          >
            {progress.output || (progress.status === "installing" ? "Waiting for output..." : "(no output)")}
          </div>
        </div>

        {progress.status !== "installing" && (
          <div className="flex justify-end mt-4">
            <button
              onClick={onClose}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm transition-colors"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function AgentRow({
  agent,
  onInstall,
  installing,
}: {
  agent: AgentInstallStatus;
  onInstall: (name: string, reinstall?: boolean) => void;
  installing: string | null;
}) {
  const isInstalling = installing === agent.agent_name;

  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-800/30 transition-colors">
      <div className="flex items-center gap-3 min-w-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">{agent.display_name}</span>
            <span className="text-xs text-gray-500 font-mono">{agent.agent_name}</span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{agent.description}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-4">
        {agent.installed && agent.version && (
          <span className="text-xs text-gray-500 font-mono">{agent.version}</span>
        )}
        <StatusBadge installed={agent.installed} />
        {agent.installed ? (
          <button
            onClick={() => onInstall(agent.agent_name, true)}
            disabled={isInstalling}
            className="text-xs px-2 py-1 text-gray-400 hover:text-white hover:bg-gray-700/50 disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors inline-flex items-center gap-1"
            title="Reinstall agent"
          >
            {isInstalling ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <RotateCcw className="w-3 h-3" />
            )}
            Reinstall
          </button>
        ) : (
          <button
            onClick={() => onInstall(agent.agent_name)}
            disabled={isInstalling}
            className="text-xs px-2.5 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded transition-colors inline-flex items-center gap-1"
          >
            {isInstalling ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                Installing...
              </>
            ) : (
              <>
                <Download className="w-3 h-3" />
                Install
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

export default function AgentManagementPanel({ serverId }: { serverId: number }) {
  const [status, setStatus] = useState<AgentManagementStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<InstallProgress | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getAgentStatus(serverId);
      setStatus(result);
    } catch {
      setError("Failed to check agent status");
    } finally {
      setLoading(false);
    }
  }, [serverId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleInstall = async (agentName: string) => {
    const agent = agents.find((a) => a.agent_name === agentName);
    const displayName = agent?.display_name || agentName;

    setInstalling(agentName);
    setError(null);
    setProgress({ agentName, displayName, status: "installing", output: "" });

    let hadError = false;

    try {
      await installAgentStream(serverId, agentName, (line, type) => {
        if (type === "error") {
          hadError = true;
          setProgress((prev) =>
            prev ? { ...prev, status: "error", error: line } : prev,
          );
        } else if (type === "complete") {
          if (!hadError) {
            setProgress((prev) =>
              prev ? { ...prev, status: "success", message: `${displayName} installed successfully` } : prev,
            );
          }
          load();
        } else if (type === "output" && line) {
          setProgress((prev) =>
            prev ? { ...prev, output: (prev.output || "") + line + "\n" } : prev,
          );
        }
      });
    } catch {
      setProgress({
        agentName,
        displayName,
        status: "error",
        error: "Install request failed — server may have timed out",
      });
    } finally {
      setInstalling(null);
    }
  };

  if (loading && !status) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-xs py-2">
        <Loader2 className="w-3 h-3 animate-spin" />
        Checking agents...
      </div>
    );
  }

  const agents = status?.by_user?.[0]?.agents ?? status?.agents ?? [];

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-300">Agents</span>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-gray-500 hover:text-gray-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>
      {error && (
        <p className="text-red-400 text-xs px-3 py-1">{error}</p>
      )}

      <div>
        {agents.map((agent) => (
          <AgentRow
            key={agent.agent_name}
            agent={agent}
            onInstall={handleInstall}
            installing={installing}
          />
        ))}
      </div>

      {progress && (
        <InstallDialog
          progress={progress}
          onClose={() => setProgress(null)}
        />
      )}
    </div>
  );
}