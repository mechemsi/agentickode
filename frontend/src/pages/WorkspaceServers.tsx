// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  Eye,
  EyeOff,
  FolderOpen,
  GitBranch,
  History,
  KeyRound,
  Loader2,
  Monitor,
  Pencil,
  Plus,
  RefreshCw,
  ScanSearch,
  Server,
  SquareTerminal,
  Trash2,
  Wifi,
} from "lucide-react";
import {
  createWorkspaceServer,
  deleteWorkspaceServer,
  deployKeyToServer,
  getWorkspaceServers,
  retryServerSetup,
  scanWorkspaceServer,
  setWorkerUserPassword,
  testWorkspaceServer,
  updateWorkspaceServer,
} from "../api";
import { useConfirm } from "../components/shared/ConfirmDialog";
import AgentManagementPanel from "../components/servers/AgentManagementPanel";
import GitAccessPanel from "../components/servers/GitAccessPanel";
import GitConnectionsPanel from "../components/servers/GitConnectionsPanel";
import ProjectsPanel from "../components/servers/ProjectsPanel";
import ServerHistoryPanel from "../components/servers/ServerHistoryPanel";
import WorkspaceServerForm from "../components/servers/WorkspaceServerForm";
import TerminalPanel from "../components/runs/TerminalPanel";
import { useToast } from "../components/shared/Toast";
import type { WorkspaceServer as WSType } from "../types";
import { generateSSHConfig } from "../utils/vscode";

const statusColor: Record<string, string> = {
  online: "bg-green-500",
  error: "bg-red-500",
  offline: "bg-red-500",
  unknown: "bg-yellow-500",
  setting_up: "bg-blue-500 animate-pulse",
  setup_failed: "bg-red-500",
};

const STEP_LABELS: Record<string, string> = {
  ssh_test: "SSH Test",
  install_system_deps: "System Deps",
  create_worker_user: "Worker User",
  create_workspace_dir: "Workspace Dir",
  install_agents: "Install Agents",
  sync_agents: "Sync Agents",
  generate_ssh_key: "SSH Key",
  discover: "Discovery",
  mark_online: "Finalize",
};

/** Check if a running step looks stuck (>10 min since timestamp). */
function isStepStuck(entry: { status: string; timestamp?: string }): boolean {
  if (entry.status !== "running" || !entry.timestamp) return false;
  const elapsed = Date.now() - new Date(entry.timestamp).getTime();
  return elapsed > 10 * 60 * 1000;
}

function SetupProgress({ server, onForceRetry }: { server: WSType; onForceRetry?: () => void }) {
  const log = server.setup_log;
  if (!log) return null;

  const steps = Object.entries(log);
  const completed = steps.filter(([, v]) => v.status === "completed").length;
  const failed = steps.find(([, v]) => v.status === "failed");
  const running = steps.find(([, v]) => v.status === "running");
  const stuck = running ? isStepStuck(running[1]) : false;

  return (
    <div className="mt-2 pl-5">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-xs text-gray-400">
          Setup: {completed}/{steps.length} steps
        </span>
        {running && !stuck && (
          <span className="text-xs text-blue-400 inline-flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            {STEP_LABELS[running[0]] || running[0]}
          </span>
        )}
        {running && stuck && (
          <span className="text-xs text-yellow-400 inline-flex items-center gap-1">
            ⚠ {STEP_LABELS[running[0]] || running[0]} appears stuck
            {onForceRetry && (
              <button
                onClick={onForceRetry}
                className="ml-1 text-yellow-300 hover:text-yellow-200 underline"
              >
                Force Re-Setup
              </button>
            )}
          </span>
        )}
        {failed && (
          <span className="text-xs text-red-400">
            Failed: {STEP_LABELS[failed[0]] || failed[0]}
          </span>
        )}
      </div>
      <div className="flex gap-1">
        {steps.map(([name, entry]) => (
          <div
            key={name}
            title={`${STEP_LABELS[name] || name}: ${entry.status}${isStepStuck(entry) ? " (stuck)" : ""}${entry.error ? ` - ${entry.error}` : ""}`}
            className={`h-1.5 flex-1 rounded-full ${
              entry.status === "completed"
                ? "bg-green-500"
                : entry.status === "running"
                  ? isStepStuck(entry) ? "bg-yellow-500 animate-pulse" : "bg-blue-500 animate-pulse"
                  : entry.status === "failed"
                    ? "bg-red-500"
                    : "bg-gray-700"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

export default function WorkspaceServers() {
  const [servers, setServers] = useState<WSType[]>([]);
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [agentsExpanded, setAgentsExpanded] = useState<Set<number>>(new Set());
  const [gitExpanded, setGitExpanded] = useState<Set<number>>(new Set());
  const [projectsExpanded, setProjectsExpanded] = useState<Set<number>>(new Set());
  const [terminalExpanded, setTerminalExpanded] = useState<Set<number>>(new Set());
  const [historyExpanded, setHistoryExpanded] = useState<Set<number>>(new Set());
  const [gitTokensExpanded, setGitTokensExpanded] = useState<Set<number>>(new Set());
  const [sshConfigExpanded, setSshConfigExpanded] = useState<Set<number>>(new Set());
  const [setupExpanded, setSetupExpanded] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [deployingKey, setDeployingKey] = useState<number | null>(null);
  const [deployPassword, setDeployPassword] = useState("");
  const [deployLoading, setDeployLoading] = useState(false);
  const [workerPassword, setWorkerPassword] = useState("");
  const [workerPasswordLoading, setWorkerPasswordLoading] = useState(false);
  const [showPassword, setShowPassword] = useState<number | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null); // "test-3", "scan-3", etc.
  const [initialLoading, setInitialLoading] = useState(true);
  const toast = useToast();
  const confirm = useConfirm();

  const toggleSet = (setter: React.Dispatch<React.SetStateAction<Set<number>>>, id: number) =>
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const load = async (check?: boolean) => {
    const data = await getWorkspaceServers(check);
    setServers(data);
    setInitialLoading(false);
  };
  useEffect(() => {
    load(true); // Check connectivity on first load
    // Poll for setup progress (without re-pinging each time)
    const interval = setInterval(() => load(), 5000);
    return () => clearInterval(interval);
  }, []);

  const handleCreate = async (data: Record<string, unknown>) => {
    setLoading(true);
    setError(null);
    try {
      await createWorkspaceServer(data as unknown as Parameters<typeof createWorkspaceServer>[0]);
      setAdding(false);
      toast.success("Server added — setup running in background");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create server");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async (id: number, data: Record<string, unknown>) => {
    try {
      await updateWorkspaceServer(id, data as unknown as Parameters<typeof updateWorkspaceServer>[1]);
      setEditing(null);
      toast.success("Server updated");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update server");
    }
  };

  const handleDelete = async (id: number) => {
    const ok = await confirm({
      title: "Delete Server",
      message: "Delete this workspace server? All associated agents and data will be removed.",
      confirmLabel: "Delete",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await deleteWorkspaceServer(id);
      toast.success("Server deleted");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete server");
    }
  };

  const handleTest = async (id: number) => {
    setBusyAction(`test-${id}`);
    try {
      const result = await testWorkspaceServer(id);
      if (result.success) {
        toast.success(`SSH OK (${result.latency_ms}ms)`);
        setDeployingKey(null);
      } else {
        toast.error(`SSH failed: ${result.error}`);
        setDeployingKey(id);
        setDeployPassword("");
      }
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "SSH test failed");
    } finally {
      setBusyAction(null);
    }
  };

  const handleDeployKey = async (id: number) => {
    setDeployLoading(true);
    try {
      const result = await deployKeyToServer(id, deployPassword);
      if (result.success) {
        toast.success("SSH key deployed successfully");
        setDeployingKey(null);
        setDeployPassword("");
      } else {
        toast.error(`Key deploy failed: ${result.error}`);
      }
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Key deploy failed");
    } finally {
      setDeployLoading(false);
    }
  };

  const handleScan = async (id: number) => {
    setBusyAction(`scan-${id}`);
    try {
      const result = await scanWorkspaceServer(id);
      toast.info(
        `Found ${result.agents_found} agents, ${result.projects_found} projects (${result.projects_imported} imported)`,
      );
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Scan failed");
      load();
    } finally {
      setBusyAction(null);
    }
  };

  const handleSetWorkerPassword = async (id: number) => {
    setWorkerPasswordLoading(true);
    try {
      const result = await setWorkerUserPassword(id, workerPassword);
      if (result.success) {
        toast.success("Worker user password set");
        setWorkerPassword("");
        load();
      } else {
        toast.error(`Failed: ${result.error}`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to set password");
    } finally {
      setWorkerPasswordLoading(false);
    }
  };

  const handleRetrySetup = async (id: number) => {
    const password = window.prompt(
      "Enter root/SSH password for this server (leave empty if SSH key is already deployed):",
    );
    if (password === null) return; // cancelled
    setBusyAction(`retry-${id}`);
    try {
      await retryServerSetup(id, password || undefined);
      toast.info("Setup retrying...");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Server className="w-5 h-5 text-blue-400" />
          Workspace Servers
        </h1>
        <div className="flex gap-2">
          <button
            onClick={() => { setBusyAction("check-all"); load(true).finally(() => setBusyAction(null)); }}
            disabled={busyAction === "check-all"}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-200 rounded-lg text-sm inline-flex items-center gap-1.5 transition-colors"
          >
            {busyAction === "check-all" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wifi className="w-4 h-4" />}
            {busyAction === "check-all" ? "Checking..." : "Check All"}
          </button>
          <button
            onClick={() => setAdding(true)}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm inline-flex items-center gap-1.5 shadow-sm shadow-blue-900/30 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          >
            <Plus className="w-4 h-4" />
            Add Server
          </button>
        </div>
      </div>

      {adding && (
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-5 mb-4 animate-fade-in">
          {error && (
            <p className="text-red-400 text-sm mb-3">{error}</p>
          )}
          <WorkspaceServerForm
            onSubmit={handleCreate}
            onCancel={() => { setAdding(false); setError(null); }}
            loading={loading}
          />
        </div>
      )}

      <div className="space-y-3">
        {servers.map((s) => (
          <div key={s.id} className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 hover:border-gray-700/60 hover:bg-gray-900/60 transition-all group backdrop-blur-sm">
            {editing === s.id ? (
              <WorkspaceServerForm
                initial={{
                  name: s.name,
                  hostname: s.hostname,
                  port: s.port,
                  username: s.username,
                  ssh_key_path: s.ssh_key_path || "",
                  worker_user: s.worker_user || "coder",
                  workspace_root: s.workspace_root || "",
                }}
                onSubmit={(data) => handleUpdate(s.id, data)}
                onCancel={() => setEditing(null)}
                isEdit
              />
            ) : (
              <>
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-2.5 h-2.5 rounded-full ring-2 ring-gray-900 ${statusColor[s.status] || statusColor.unknown}`}
                    />
                    <span className="font-medium text-white">{s.name}</span>
                    <span className="text-gray-500 text-sm font-mono">
                      {s.hostname}:{s.port}
                    </span>
                    {s.status === "setting_up" && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 inline-flex items-center gap-1">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Setting up...
                      </span>
                    )}
                    {s.status !== "setting_up" && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-700/50 text-gray-400">
                        {s.agent_count} agents · {s.project_count} projects
                        {s.last_seen_at && (
                          <span className="ml-1 text-gray-500" title={`Last seen: ${new Date(s.last_seen_at).toLocaleString()}`}>
                            · {(() => {
                              const ago = Date.now() - new Date(s.last_seen_at).getTime();
                              if (ago < 60_000) return "just now";
                              if (ago < 3600_000) return `${Math.floor(ago / 60_000)}m ago`;
                              if (ago < 86400_000) return `${Math.floor(ago / 3600_000)}h ago`;
                              return `${Math.floor(ago / 86400_000)}d ago`;
                            })()}
                          </span>
                        )}
                      </span>
                    )}
                  </div>
                  <div className="flex gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                    {s.setup_log && (
                      <button
                        onClick={() => toggleSet(setSetupExpanded, s.id)}
                        className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                      >
                        {setupExpanded.has(s.id) ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                        Setup Log
                      </button>
                    )}
                    {(s.status === "setup_failed" || s.status === "online" || s.status === "setting_up") && (
                      <button
                        onClick={() => handleRetrySetup(s.id)}
                        disabled={busyAction === `retry-${s.id}`}
                        className={`text-xs disabled:opacity-50 inline-flex items-center gap-1 px-2 py-1 rounded transition-colors ${
                          s.status === "setup_failed" || s.status === "setting_up"
                            ? "text-yellow-400 hover:text-yellow-300 hover:bg-yellow-900/20"
                            : "text-gray-400 hover:text-white hover:bg-gray-700/50"
                        }`}
                      >
                        {busyAction === `retry-${s.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                        {busyAction === `retry-${s.id}` ? "Running..." : s.status === "setup_failed" ? "Retry Setup" : s.status === "setting_up" ? "Restart Setup" : "Re-Setup"}
                      </button>
                    )}
                    <button
                      onClick={() => toggleSet(setAgentsExpanded, s.id)}
                      className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      {agentsExpanded.has(s.id) ? "Collapse" : "Agents"}
                    </button>
                    <button
                      onClick={() => toggleSet(setGitExpanded, s.id)}
                      className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      <GitBranch className="w-3 h-3" />
                      Git Access
                    </button>
                    <button
                      onClick={() => toggleSet(setGitTokensExpanded, s.id)}
                      className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      <KeyRound className="w-3 h-3" />
                      Git Tokens
                    </button>
                    <button
                      onClick={() => toggleSet(setProjectsExpanded, s.id)}
                      className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      <FolderOpen className="w-3 h-3" />
                      Projects
                    </button>
                    <button
                      onClick={() => toggleSet(setHistoryExpanded, s.id)}
                      className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      <History className="w-3 h-3" />
                      History
                    </button>
                    <button
                      onClick={() => toggleSet(setSshConfigExpanded, s.id)}
                      className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      <Monitor className="w-3 h-3" />
                      VS Code
                    </button>
                    <button
                      onClick={() => toggleSet(setTerminalExpanded, s.id)}
                      className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      <SquareTerminal className="w-3 h-3" />
                      {terminalExpanded.has(s.id) ? "Close Terminal" : "Terminal"}
                    </button>
                    <button
                      onClick={() => handleTest(s.id)}
                      disabled={busyAction === `test-${s.id}`}
                      className="text-xs text-gray-400 hover:text-white disabled:opacity-50 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      {busyAction === `test-${s.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wifi className="w-3 h-3" />}
                      {busyAction === `test-${s.id}` ? "Testing..." : "Test"}
                    </button>
                    <button
                      onClick={() => handleScan(s.id)}
                      disabled={busyAction === `scan-${s.id}`}
                      className="text-xs text-gray-400 hover:text-white disabled:opacity-50 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      {busyAction === `scan-${s.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <ScanSearch className="w-3 h-3" />}
                      {busyAction === `scan-${s.id}` ? "Scanning..." : "Scan"}
                    </button>
                    <button
                      onClick={() => setEditing(s.id)}
                      className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      <Pencil className="w-3 h-3" />
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(s.id)}
                      className="text-xs text-red-400 hover:text-red-300 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-red-900/20 transition-colors"
                    >
                      <Trash2 className="w-3 h-3" />
                      Delete
                    </button>
                  </div>
                </div>
                {s.error_message && (
                  <pre className="text-red-400 text-xs mt-2 pl-5 whitespace-pre-wrap break-all">{s.error_message}</pre>
                )}
                {(s.status === "setting_up" || s.status === "setup_failed") && s.setup_log && (
                  <SetupProgress server={s} onForceRetry={() => handleRetrySetup(s.id)} />
                )}
                {setupExpanded.has(s.id) && s.setup_log && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <h4 className="text-xs text-gray-400 mb-2 font-medium">Setup Log</h4>
                    <div className="space-y-1.5">
                      {Object.entries(s.setup_log).map(([name, entry]) => (
                        <div key={name}>
                          <div className="flex items-center gap-2 text-xs">
                            <span className={`w-2 h-2 rounded-full shrink-0 ${
                              entry.status === "completed" ? "bg-green-500" :
                              entry.status === "running" ? "bg-blue-500 animate-pulse" :
                              entry.status === "failed" ? "bg-red-500" :
                              "bg-gray-600"
                            }`} />
                            <span className="text-gray-300 w-28 shrink-0">{STEP_LABELS[name] || name}</span>
                            <span className={
                              entry.status === "completed" ? "text-green-400" :
                              entry.status === "running" ? "text-blue-400" :
                              entry.status === "failed" ? "text-red-400" :
                              "text-gray-500"
                            }>{entry.status}</span>
                          </div>
                          {entry.error && (
                            <pre className="text-red-400/80 text-xs mt-1 ml-5 whitespace-pre-wrap break-all bg-red-950/20 border border-red-900/30 rounded px-2 py-1 max-h-32 overflow-y-auto">
                              {entry.error}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {deployingKey === s.id && (
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <KeyRound className="w-4 h-4 text-yellow-400 shrink-0" />
                    <span className="text-xs text-gray-400 shrink-0">Deploy SSH key:</span>
                    <input
                      type="password"
                      placeholder="Server password"
                      value={deployPassword}
                      onChange={(e) => setDeployPassword(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && deployPassword) handleDeployKey(s.id);
                      }}
                      className="flex-1 px-2.5 py-1 bg-gray-800 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50"
                    />
                    <button
                      onClick={() => handleDeployKey(s.id)}
                      disabled={!deployPassword || deployLoading}
                      className="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors"
                    >
                      {deployLoading ? "Deploying..." : "Deploy Key"}
                    </button>
                    <button
                      onClick={() => { setDeployingKey(null); setDeployPassword(""); }}
                      className="text-xs text-gray-500 hover:text-gray-300 px-2 py-1"
                    >
                      Cancel
                    </button>
                  </div>
                )}
                {agentsExpanded.has(s.id) && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <AgentManagementPanel serverId={s.id} />
                  </div>
                )}
                {gitExpanded.has(s.id) && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <GitAccessPanel serverId={s.id} />
                  </div>
                )}
                {gitTokensExpanded.has(s.id) && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <h4 className="text-xs text-gray-400 mb-2 font-medium flex items-center gap-1.5">
                      <KeyRound className="w-3.5 h-3.5" />
                      Git Tokens
                    </h4>
                    <GitConnectionsPanel serverId={s.id} />
                  </div>
                )}
                {projectsExpanded.has(s.id) && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <ProjectsPanel serverId={s.id} server={s} />
                  </div>
                )}
                {terminalExpanded.has(s.id) && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <TerminalPanel serverId={s.id} />
                  </div>
                )}
                {historyExpanded.has(s.id) && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <ServerHistoryPanel serverId={s.id} />
                  </div>
                )}
                {sshConfigExpanded.has(s.id) && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 animate-fade-in">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-gray-300">SSH Config for VS Code Remote-SSH</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(generateSSHConfig(s));
                          toast.success("SSH config copied to clipboard");
                        }}
                        className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                      >
                        <ClipboardCopy className="w-3 h-3" />
                        Copy to Clipboard
                      </button>
                    </div>
                    <pre className="text-xs text-gray-300 bg-gray-950/60 border border-gray-800/50 rounded-lg p-3 font-mono whitespace-pre overflow-x-auto">
                      {generateSSHConfig(s)}
                    </pre>
                    <p className="text-xs text-gray-500 mt-2">
                      Add this to <code className="text-gray-400">~/.ssh/config</code>, then use the Open in VS Code buttons on each project.
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      JetBrains Gateway also reads <code className="text-gray-400">~/.ssh/config</code> — the same config works for both VS Code and JetBrains IDEs.
                    </p>
                    {s.worker_user && (
                      <div className="mt-3 pt-3 border-t border-gray-700/40">
                        <span className="text-xs font-medium text-gray-300">Worker User Password</span>
                        {s.worker_user_password && (
                          <div className="flex items-center gap-2 mt-1.5">
                            <code className="text-xs text-gray-300 bg-gray-950/60 border border-gray-800/50 rounded px-2 py-1 font-mono">
                              {showPassword === s.id ? s.worker_user_password : "••••••••"}
                            </code>
                            <button
                              onClick={() => setShowPassword(showPassword === s.id ? null : s.id)}
                              className="text-xs text-gray-400 hover:text-white p-1 rounded hover:bg-gray-700/50 transition-colors"
                              title={showPassword === s.id ? "Hide password" : "Show password"}
                            >
                              {showPassword === s.id ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                            </button>
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(s.worker_user_password!);
                                toast.success("Password copied");
                              }}
                              className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 p-1 rounded hover:bg-gray-700/50 transition-colors"
                              title="Copy password"
                            >
                              <ClipboardCopy className="w-3 h-3" />
                            </button>
                          </div>
                        )}
                        <div className="flex items-center gap-2 mt-2">
                          <input
                            type="password"
                            placeholder={s.worker_user_password ? "Change password" : "Set password for VS Code SSH"}
                            value={workerPassword}
                            onChange={(e) => setWorkerPassword(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && workerPassword) handleSetWorkerPassword(s.id);
                            }}
                            className="flex-1 px-2.5 py-1 bg-gray-800 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50"
                          />
                          <button
                            onClick={() => handleSetWorkerPassword(s.id)}
                            disabled={!workerPassword || workerPasswordLoading}
                            className="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors"
                          >
                            {workerPasswordLoading ? "Setting..." : "Set Password"}
                          </button>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          Set a password so VS Code Remote-SSH can connect without SSH keys.
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        ))}
        {initialLoading && servers.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500 bg-gray-900/40 border border-gray-800/60 rounded-xl backdrop-blur-sm">
            <Loader2 className="w-6 h-6 mb-2 text-gray-500 animate-spin" />
            <p className="text-sm">Loading servers...</p>
          </div>
        )}
        {!initialLoading && servers.length === 0 && !adding && (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500 bg-gray-900/40 border border-gray-800/60 rounded-xl backdrop-blur-sm">
            <Server className="w-8 h-8 mb-2 text-gray-600" />
            <p className="text-sm">No workspace servers configured yet.</p>
          </div>
        )}
      </div>
    </>
  );
}