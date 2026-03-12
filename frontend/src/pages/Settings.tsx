// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import {
  Activity,
  Check,
  Copy,
  Cpu,
  Database,
  Globe,
  Heart,
  Key,
  Loader2,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Server,
  Settings as SettingsIcon,
  Trash2,
} from "lucide-react";
import { getHealth, getSSHKeys, createSSHKey, deleteSSHKey, getAppSettings, updateAppSetting, getSupportedAgents, createOllamaServer, deleteOllamaServer, getOllamaServers, refreshOllamaModels, updateOllamaServer } from "../api";
import type { HealthResponse, OllamaServer, SSHKey } from "../types";
import { AGENT_NAMES } from "../types";
import type { ElementType } from "react";
import { useConfirm } from "../components/shared/ConfirmDialog";
import { useToast } from "../components/shared/Toast";
import BackupExport from "../components/settings/BackupExport";
import BackupImport from "../components/settings/BackupImport";
import NotificationSettings from "../components/settings/NotificationSettings";
import OllamaServerForm from "../components/settings/OllamaServerForm";
import QueueSchedule from "../components/settings/QueueSchedule";

const serviceIcons: Record<string, ElementType> = {
  database: Database,
  ollama: Cpu,
  openhands: Globe,
  redis: Database,
  chromadb: Database,
};

function getServiceIcon(name: string): ElementType {
  if (name.startsWith("ollama:")) return Cpu;
  return serviceIcons[name] ?? Activity;
}

export default function Settings() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [keys, setKeys] = useState<SSHKey[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [keyComment, setKeyComment] = useState("");
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [defaultAgents, setDefaultAgents] = useState<string[]>([]);
  const [agentsDirty, setAgentsDirty] = useState(false);
  const [savingAgents, setSavingAgents] = useState(false);
  const [availableAgents, setAvailableAgents] = useState<string[]>([...AGENT_NAMES]);
  const [healthLoading, setHealthLoading] = useState(true);
  const [ollamaServers, setOllamaServers] = useState<OllamaServer[]>([]);
  const [addingServer, setAddingServer] = useState(false);
  const [editingServer, setEditingServer] = useState<number | null>(null);
  const confirm = useConfirm();
  const toast = useToast();

  const loadHealth = async () => {
    try {
      setHealth(await getHealth());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };

  const loadKeys = async () => {
    try {
      setKeys(await getSSHKeys());
    } catch {
      /* ignore – keys section just stays empty */
    }
  };

  const loadSettings = async () => {
    try {
      const settings = await getAppSettings();
      if (Array.isArray(settings.default_agents)) {
        setDefaultAgents(settings.default_agents as string[]);
      }
    } catch {
      /* ignore */
    }
  };

  const loadOllamaServers = async () => { try { setOllamaServers(await getOllamaServers()); } catch { /* ignore */ } };

  const handleCreateServer = async (data: { name: string; url: string }) => {
    await createOllamaServer(data);
    setAddingServer(false);
    loadOllamaServers();
  };

  const handleUpdateServer = async (id: number, data: { name: string; url: string }) => {
    await updateOllamaServer(id, data);
    setEditingServer(null);
    loadOllamaServers();
  };

  const handleDeleteServer = async (id: number) => {
    const ok = await confirm({ title: "Delete Ollama Server", message: "Delete this Ollama server? Role assignments using it will need reconfiguring.", confirmLabel: "Delete", variant: "danger" });
    if (!ok) return;
    try { await deleteOllamaServer(id); toast.success("Ollama server deleted"); loadOllamaServers(); } catch { toast.error("Cannot delete: server has active role assignments."); }
  };

  const handleRefreshServer = async (id: number) => { await refreshOllamaModels(id); loadOllamaServers(); };

  useEffect(() => {
    loadHealth().finally(() => setHealthLoading(false));
    loadKeys();
    loadSettings();
    loadOllamaServers();
    getSupportedAgents()
      .then((agents) => setAvailableAgents(agents.map((a) => a.name)))
      .catch(() => {/* keep fallback AGENT_NAMES */});
    const interval = setInterval(loadHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleCreate = async () => {
    if (!keyName.trim()) return;
    setCreating(true);
    try {
      await createSSHKey({ name: keyName.trim(), comment: keyComment.trim() || undefined });
      toast.success(`Key "${keyName}" generated`);
      setKeyName("");
      setKeyComment("");
      setShowForm(false);
      await loadKeys();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (name: string) => {
    const ok = await confirm({
      title: "Delete SSH Key",
      message: `Delete key "${name}"? This cannot be undone.`,
      confirmLabel: "Delete",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await deleteSSHKey(name);
      toast.success(`Key "${name}" deleted`);
      await loadKeys();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const copyPublicKey = async (key: SSHKey) => {
    if (!key.public_key) return;
    await navigator.clipboard.writeText(key.public_key);
    setCopied(key.name);
    setTimeout(() => setCopied(null), 2000);
  };

  const toggleAgent = (agent: string) => {
    setDefaultAgents((prev) =>
      prev.includes(agent) ? prev.filter((a) => a !== agent) : [...prev, agent],
    );
    setAgentsDirty(true);
  };

  const saveDefaultAgents = async () => {
    setSavingAgents(true);
    try {
      await updateAppSetting("default_agents", defaultAgents);
      toast.success("Default agents saved");
      setAgentsDirty(false);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSavingAgents(false);
    }
  };

  return (
    <>
      <h1 className="text-xl font-semibold mb-6 flex items-center gap-2">
        <SettingsIcon className="w-5 h-5 text-blue-400" />
        Settings & Health
      </h1>

      {healthLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
          <span className="ml-2 text-sm text-gray-400">Checking services...</span>
        </div>
      )}

      {!healthLoading && error && (
        <div className="bg-red-900/30 border border-red-800/50 rounded-xl p-4 mb-5 text-sm text-red-300">
          Failed to fetch health: {error}
        </div>
      )}

      {!healthLoading && health && (
        <div className="space-y-5">
          {/* Overall Status */}
          <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 backdrop-blur-sm">
            <div className="flex items-center gap-3 flex-wrap">
              <Heart className={`w-5 h-5 ${health.status === "ok" ? "text-green-400 animate-pulse-slow" : "text-yellow-400"}`} />
              <span className="text-sm text-gray-400">Overall:</span>
              <span className={`text-sm font-semibold px-2.5 py-0.5 rounded-full ${health.status === "ok" ? "text-green-400 bg-green-500/10" : "text-yellow-400 bg-yellow-500/10"}`}>
                {health.status}
              </span>
              <span className="text-sm text-gray-500">
                · Worker: {health.worker_running ? "running" : "stopped"}
                · Active runs: {health.active_runs}
              </span>
            </div>
          </div>

          {/* Service Health Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {health.services.map((s) => {
              const Icon = getServiceIcon(s.name);
              const isOk = s.status === "ok";
              const isNotConfigured = s.status === "not_configured";
              const colorClass = isOk
                ? "border-green-800/40 bg-green-500/5"
                : isNotConfigured
                  ? "border-gray-700/40 bg-gray-500/5"
                  : "border-red-800/40 bg-red-500/5";
              const iconColor = isOk
                ? "text-green-400/60"
                : isNotConfigured
                  ? "text-gray-400/60"
                  : "text-red-400/60";
              const badgeClass = isOk
                ? "text-green-400 bg-green-500/10"
                : isNotConfigured
                  ? "text-gray-400 bg-gray-500/10"
                  : "text-red-400 bg-red-500/10";
              return (
                <div
                  key={s.name}
                  className={`rounded-xl p-4 border backdrop-blur-sm transition-all hover:scale-[1.01] ${colorClass}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-sm inline-flex items-center gap-2">
                      <Icon className={`w-4 h-4 ${iconColor}`} />
                      {s.name}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${badgeClass}`}>
                      {isNotConfigured ? "not configured" : s.status}
                    </span>
                  </div>
                  {s.latency_ms != null && (
                    <span className="text-xs text-gray-500 font-mono">{s.latency_ms}ms</span>
                  )}
                  {s.error && (
                    <p className="text-xs text-red-400 mt-1.5">{s.error}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Default Agents for New Servers */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Package className="w-5 h-5 text-blue-400" />
            Default Agents
          </h2>
          {agentsDirty && (
            <button
              onClick={saveDefaultAgents}
              disabled={savingAgents}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              <Save className="w-3.5 h-3.5" />
              {savingAgents ? "Saving..." : "Save"}
            </button>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Agents selected here will be auto-installed when a new workspace server is added.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {availableAgents.map((agent) => (
            <button
              key={agent}
              onClick={() => toggleAgent(agent)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-all ${
                defaultAgents.includes(agent)
                  ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
                  : "border-gray-700/50 bg-gray-800/50 text-gray-400 hover:border-gray-600"
              }`}
            >
              <span className={`w-4 h-4 rounded border flex items-center justify-center ${
                defaultAgents.includes(agent) ? "border-blue-500 bg-blue-500" : "border-gray-600"
              }`}>
                {defaultAgents.includes(agent) && <Check className="w-3 h-3 text-white" />}
              </span>
              {agent}
            </button>
          ))}
        </div>
      </div>

      {/* Queue Schedule */}
      <QueueSchedule />

      {/* Ollama Servers */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Server className="w-5 h-5 text-blue-400" />
            Ollama Servers
          </h2>
          <button onClick={() => setAddingServer(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">
            <Plus className="w-3.5 h-3.5" /> Add Server
          </button>
        </div>
        {addingServer && (
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4 mb-4">
            <OllamaServerForm onSubmit={handleCreateServer} onCancel={() => setAddingServer(false)} />
          </div>
        )}
        <div className="space-y-2">
          {ollamaServers.map((s) => (
            <div key={s.id} className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 backdrop-blur-sm group">
              {editingServer === s.id ? (
                <OllamaServerForm initial={{ name: s.name, url: s.url }} onSubmit={(data) => handleUpdateServer(s.id, data)} onCancel={() => setEditingServer(null)} />
              ) : (
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-3">
                    <span className={`w-2.5 h-2.5 rounded-full ring-2 ring-gray-900 ${s.status === "online" ? "bg-green-500" : s.status === "error" ? "bg-red-500" : "bg-yellow-500"}`} />
                    <span className="font-medium text-white">{s.name}</span>
                    <span className="text-gray-500 text-sm font-mono">{s.url}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-700/50 text-gray-400">{s.cached_models?.length || 0} models</span>
                  </div>
                  <div className="flex gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => handleRefreshServer(s.id)} className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"><RefreshCw className="w-3 h-3" /> Refresh</button>
                    <button onClick={() => setEditingServer(s.id)} className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"><Pencil className="w-3 h-3" /> Edit</button>
                    <button onClick={() => handleDeleteServer(s.id)} className="text-xs text-red-400 hover:text-red-300 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-red-900/20 transition-colors"><Trash2 className="w-3 h-3" /> Delete</button>
                  </div>
                </div>
              )}
              {s.error_message && <p className="text-red-400 text-xs mt-2 pl-5">{s.error_message}</p>}
            </div>
          ))}
          {ollamaServers.length === 0 && !addingServer && (
            <div className="flex flex-col items-center justify-center py-8 text-gray-500">
              <Server className="w-8 h-8 mb-2 text-gray-600" />
              <p className="text-sm">No Ollama servers configured yet.</p>
            </div>
          )}
        </div>
      </div>

      {/* Notification Channels */}
      <NotificationSettings />

      {/* Backup / Config Export-Import */}
      <BackupExport />
      <BackupImport />

      {/* SSH Key Management */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Key className="w-5 h-5 text-blue-400" />
            SSH Keys
          </h2>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Generate Key
          </button>
        </div>

        {showForm && (
          <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 mb-4 backdrop-blur-sm">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Key Name</label>
                <input
                  type="text"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="e.g. my-server"
                  className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Comment (optional)</label>
                <input
                  type="text"
                  value={keyComment}
                  onChange={(e) => setKeyComment(e.target.value)}
                  placeholder="e.g. autodev@production"
                  className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setShowForm(false); setKeyName(""); setKeyComment(""); }}
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !keyName.trim()}
                className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
              >
                {creating ? "Generating..." : "Generate"}
              </button>
            </div>
          </div>
        )}

        {keys.length === 0 ? (
          <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-6 text-center text-sm text-gray-500">
            No SSH keys found. Keys are auto-generated on container start.
          </div>
        ) : (
          <div className="space-y-3">
            {keys.map((k) => (
              <div
                key={k.name}
                className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 backdrop-blur-sm"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Key className="w-4 h-4 text-gray-500" />
                    <span className="text-sm font-medium">{k.name}</span>
                    {k.is_default && (
                      <span className="text-xs px-2 py-0.5 rounded-full text-blue-400 bg-blue-500/10">
                        default
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    {k.public_key && (
                      <button
                        onClick={() => copyPublicKey(k)}
                        className="p-1.5 text-gray-500 hover:text-white rounded-lg hover:bg-gray-800 transition-colors"
                        title="Copy public key"
                      >
                        {copied === k.name ? (
                          <Check className="w-3.5 h-3.5 text-green-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(k.name)}
                      className="p-1.5 text-gray-500 hover:text-red-400 rounded-lg hover:bg-gray-800 transition-colors"
                      title="Delete key"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                {k.public_key && (
                  <code className="block text-xs text-gray-500 font-mono break-all bg-gray-800/50 rounded-lg p-2 mt-1">
                    {k.public_key}
                  </code>
                )}
                <div className="text-xs text-gray-600 mt-2">
                  Created: {new Date(k.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}