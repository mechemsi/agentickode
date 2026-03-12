// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import type { ElementType } from "react";
import {
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Code,
  Cpu,
  Eye,
  Plus,
  RotateCcw,
  Save,
  Shield,
  Trash2,
  Zap,
} from "lucide-react";
import {
  getRoleConfigs,
  createRoleConfig,
  updateRoleConfig,
  deleteRoleConfig,
  resetRoleConfig,
  getPromptOverrides,
  upsertPromptOverride,
  deletePromptOverride,
  getRoleAssignments,
  updateRoleAssignments,
  deleteRoleAssignment,
  getOllamaServers,
  getWorkspaceServers,
} from "../api";
import type {
  RoleConfig,
  RolePromptOverride,
  RoleAssignment,
  RoleAssignmentInput,
  OllamaServer,
  WorkspaceServer,
} from "../types";
import { AGENT_NAMES } from "../types";
import { useConfirm } from "../components/shared/ConfirmDialog";
import { useToast } from "../components/shared/Toast";

const CLI_AGENTS = ["claude", "codex", "gemini", "kimi", "aider", "opencode"] as const;
type CliAgent = (typeof CLI_AGENTS)[number];

const ROLE_STYLE: Record<string, { icon: ElementType; border: string; text: string }> = {
  planner: { icon: Brain, border: "border-l-blue-500", text: "text-blue-400" },
  coder: { icon: Code, border: "border-l-emerald-500", text: "text-emerald-400" },
  reviewer: { icon: Eye, border: "border-l-violet-500", text: "text-violet-400" },
  fast: { icon: Zap, border: "border-l-amber-500", text: "text-amber-400" },
};

/* ── Per-Agent Prompt Overrides ───────────────────────── */

interface OverrideFormState {
  system_prompt: string;
  user_prompt_template: string;
  minimal_mode: boolean;
}

const defaultOverrideForm = (): OverrideFormState => ({
  system_prompt: "",
  user_prompt_template: "",
  minimal_mode: false,
});

const overrideToForm = (o: RolePromptOverride): OverrideFormState => ({
  system_prompt: o.system_prompt ?? "",
  user_prompt_template: o.user_prompt_template ?? "",
  minimal_mode: o.minimal_mode,
});

function AgentOverridesSection({ configName }: { configName: string }) {
  const [overrides, setOverrides] = useState<Record<CliAgent, RolePromptOverride | null>>(
    () => Object.fromEntries(CLI_AGENTS.map((a) => [a, null])) as Record<CliAgent, RolePromptOverride | null>,
  );
  const [forms, setForms] = useState<Record<CliAgent, OverrideFormState>>(
    () => Object.fromEntries(CLI_AGENTS.map((a) => [a, defaultOverrideForm()])) as Record<CliAgent, OverrideFormState>,
  );
  const [expanded, setExpanded] = useState<CliAgent | null>(null);
  const [saving, setSaving] = useState<CliAgent | null>(null);
  const toast = useToast();

  const load = async () => {
    try {
      const data = await getPromptOverrides(configName);
      const map = Object.fromEntries(CLI_AGENTS.map((a) => [a, null])) as Record<CliAgent, RolePromptOverride | null>;
      const formMap = Object.fromEntries(CLI_AGENTS.map((a) => [a, defaultOverrideForm()])) as Record<CliAgent, OverrideFormState>;
      for (const o of data) {
        const agent = o.cli_agent_name as CliAgent;
        if (CLI_AGENTS.includes(agent)) {
          map[agent] = o;
          formMap[agent] = overrideToForm(o);
        }
      }
      setOverrides(map);
      setForms(formMap);
    } catch { /* silent */ }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [configName]);

  const handleSave = async (agent: CliAgent) => {
    setSaving(agent);
    try {
      const f = forms[agent];
      await upsertPromptOverride(configName, agent, {
        system_prompt: f.system_prompt || null,
        user_prompt_template: f.user_prompt_template || null,
        minimal_mode: f.minimal_mode,
        extra_params: {},
      });
      toast.success(`Saved override for ${agent}`);
      await load();
    } catch (e) { toast.error(String(e)); } finally { setSaving(null); }
  };

  const handleDelete = async (agent: CliAgent) => {
    setSaving(agent);
    try {
      await deletePromptOverride(configName, agent);
      toast.success(`Deleted override for ${agent}`);
      await load();
    } catch (e) { toast.error(String(e)); } finally { setSaving(null); }
  };

  const updateForm = (agent: CliAgent, patch: Partial<OverrideFormState>) =>
    setForms((prev) => ({ ...prev, [agent]: { ...prev[agent], ...patch } }));

  return (
    <div className="space-y-2">
      {CLI_AGENTS.map((agent) => {
        const override = overrides[agent];
        const form = forms[agent];
        const isOpen = expanded === agent;
        const hasOverride = override !== null;
        return (
          <div key={agent} className="bg-gray-800/40 border border-gray-700/50 rounded-lg">
            <button onClick={() => setExpanded(isOpen ? null : agent)} className="w-full flex items-center justify-between px-3 py-2 text-sm">
              <div className="flex items-center gap-2">
                {isOpen ? <ChevronUp className="w-3.5 h-3.5 text-gray-500" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-500" />}
                <span className="font-mono text-gray-300">{agent}</span>
                {hasOverride && <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-400">override active</span>}
                {hasOverride && override.minimal_mode && <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400">minimal</span>}
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-gray-700/50 p-3 space-y-3">
                <div className="flex items-center gap-2">
                  <input type="checkbox" id={`minimal-${agent}`} checked={form.minimal_mode} onChange={(e) => updateForm(agent, { minimal_mode: e.target.checked })} className="w-3.5 h-3.5 accent-blue-500" />
                  <label htmlFor={`minimal-${agent}`} className="text-xs text-gray-300 cursor-pointer">Minimal mode — skip system prompt, send only the task instruction</label>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">
                    System Prompt Override{form.minimal_mode && <span className="ml-1 text-gray-500">(ignored in minimal mode)</span>}
                  </label>
                  <textarea value={form.system_prompt} onChange={(e) => updateForm(agent, { system_prompt: e.target.value })} placeholder="Leave empty to use default" rows={3} disabled={form.minimal_mode} className="w-full px-3 py-2 text-sm bg-gray-900 border border-gray-700 rounded-lg text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-y disabled:opacity-40" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">User Prompt Template Override</label>
                  <textarea value={form.user_prompt_template} onChange={(e) => updateForm(agent, { user_prompt_template: e.target.value })} placeholder="Leave empty to use default" rows={4} className="w-full px-3 py-2 text-sm bg-gray-900 border border-gray-700 rounded-lg text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-y" />
                </div>
                <div className="flex gap-2 justify-end">
                  {hasOverride && (
                    <button onClick={() => handleDelete(agent)} disabled={saving === agent} className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-red-400 hover:text-red-300 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg transition-colors">
                      <Trash2 className="w-3 h-3" /> Remove override
                    </button>
                  )}
                  <button onClick={() => handleSave(agent)} disabled={saving === agent} className="px-2.5 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors">
                    {saving === agent ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Inline Assignment Row ────────────────────────────── */

interface AssignmentRowProps {
  role: string;
  priority: number;
  draft: RoleAssignmentInput | undefined;
  existing: RoleAssignment | undefined;
  servers: OllamaServer[];
  onFieldChange: (field: keyof RoleAssignmentInput, val: string | number | null) => void;
  onDelete: () => void;
}

function AssignmentRow({ role, priority, draft, existing, servers, onFieldChange, onDelete }: AssignmentRowProps) {
  const d: RoleAssignmentInput = draft || { role, provider_type: "ollama", priority, workspace_server_id: null, ollama_server_id: null, model_name: null, agent_name: null };
  const isPrimary = priority === 0;

  const modelsFor = (serverId: number | null | undefined): string[] => {
    if (!serverId) return [];
    const server = servers.find((s) => s.id === serverId);
    if (!server?.cached_models) return [];
    return server.cached_models.map((m) => String(m.name || m.model || "")).filter(Boolean);
  };
  const models = d.provider_type === "ollama" ? modelsFor(d.ollama_server_id) : [];

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className={`text-xs w-16 ${isPrimary ? "text-gray-300 font-medium" : "text-gray-500"}`}>
        {isPrimary ? "Primary" : "Fallback"}
      </span>
      <select className="bg-gray-800/80 border border-gray-700/60 rounded-md px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40" value={d.provider_type || "ollama"} onChange={(e) => onFieldChange("provider_type", e.target.value)}>
        <option value="ollama">Ollama</option>
        <option value="agent">Agent</option>
      </select>
      {d.provider_type === "ollama" ? (
        <div className="flex gap-2 flex-1 min-w-0">
          <select className="bg-gray-800/80 border border-gray-700/60 rounded-md px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 flex-1" value={d.ollama_server_id ?? ""} onChange={(e) => onFieldChange("ollama_server_id", parseInt(e.target.value) || null)}>
            <option value="">-- server --</option>
            {servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          {models.length > 0 ? (
            <select className="bg-gray-800/80 border border-gray-700/60 rounded-md px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 flex-1" value={d.model_name ?? ""} onChange={(e) => onFieldChange("model_name", e.target.value)}>
              <option value="">-- model --</option>
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input className="bg-gray-800/80 border border-gray-700/60 rounded-md px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 flex-1" value={d.model_name ?? ""} onChange={(e) => onFieldChange("model_name", e.target.value)} placeholder="model name" />
          )}
        </div>
      ) : (
        <select className="bg-gray-800/80 border border-gray-700/60 rounded-md px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 flex-1" value={d.agent_name ?? ""} onChange={(e) => onFieldChange("agent_name", e.target.value)}>
          <option value="">-- agent --</option>
          {AGENT_NAMES.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      )}
      {existing && (
        <button onClick={onDelete} className="text-xs text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-red-900/20 transition-colors">Clear</button>
      )}
    </div>
  );
}

/* ── Main Page ────────────────────────────────────────── */

type DraftKey = string;
const draftKey = (role: string, priority: number): DraftKey => `${role}:${priority}`;

export default function RoleConfigs() {
  const [roles, setRoles] = useState<RoleConfig[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();
  const toast = useToast();

  const [newName, setNewName] = useState("");
  const [newDisplay, setNewDisplay] = useState("");
  const [newDesc, setNewDesc] = useState("");

  const [promptsOpen, setPromptsOpen] = useState<Record<string, boolean>>({});
  const [overridesOpen, setOverridesOpen] = useState<Record<string, boolean>>({});

  // Role assignment state
  const [ollamaServers, setOllamaServers] = useState<OllamaServer[]>([]);
  const [wsServers, setWsServers] = useState<WorkspaceServer[]>([]);
  const [assignments, setAssignments] = useState<RoleAssignment[]>([]);
  const [draft, setDraft] = useState<Record<DraftKey, RoleAssignmentInput>>({});
  const [scopeServerId, setScopeServerId] = useState<number | undefined>(undefined);

  const loadRoles = async () => {
    try {
      setRoles(await getRoleConfigs());
      setError(null);
    } catch (e) { setError(String(e)); }
  };

  const loadAssignments = async () => {
    const r = await getRoleAssignments(scopeServerId);
    setAssignments(r);
    const d: Record<DraftKey, RoleAssignmentInput> = {};
    for (const a of r) {
      d[draftKey(a.role, a.priority)] = {
        role: a.role,
        provider_type: a.provider_type as "ollama" | "agent",
        ollama_server_id: a.ollama_server_id,
        model_name: a.model_name,
        agent_name: a.agent_name,
        workspace_server_id: a.workspace_server_id,
        priority: a.priority,
      };
    }
    setDraft(d);
  };

  useEffect(() => {
    loadRoles();
    getOllamaServers().then(setOllamaServers).catch(() => {});
    getWorkspaceServers().then(setWsServers).catch(() => {});
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadAssignments(); }, [scopeServerId]);

  const toggle = (name: string) => setExpanded(expanded === name ? null : name);

  const handleSaveField = async (role: RoleConfig, field: string, value: string | number) => {
    setSaving(role.agent_name);
    try {
      await updateRoleConfig(role.agent_name, { [field]: value });
      toast.success(`Updated ${role.display_name}`);
      await loadRoles();
    } catch (e) { toast.error(String(e)); } finally { setSaving(null); }
  };

  const handleCreate = async () => {
    if (!newName.trim() || !newDisplay.trim()) return;
    try {
      await createRoleConfig({ agent_name: newName.trim(), display_name: newDisplay.trim(), description: newDesc.trim() });
      toast.success(`Role "${newName}" created`);
      setNewName(""); setNewDisplay(""); setNewDesc(""); setShowForm(false);
      await loadRoles();
    } catch (e) { toast.error(String(e)); }
  };

  const handleDelete = async (role: RoleConfig) => {
    const ok = await confirm({ title: "Delete Role", message: `Delete role "${role.display_name}"? This cannot be undone.`, confirmLabel: "Delete", variant: "danger" });
    if (!ok) return;
    try {
      await deleteRoleConfig(role.agent_name);
      toast.success(`Deleted "${role.agent_name}"`);
      await loadRoles();
    } catch (e) { toast.error(String(e)); }
  };

  const handleReset = async (role: RoleConfig) => {
    const ok = await confirm({ title: "Reset to Default", message: `Reset "${role.display_name}" prompts to factory defaults?`, confirmLabel: "Reset", variant: "danger" });
    if (!ok) return;
    try {
      await resetRoleConfig(role.agent_name);
      toast.success(`Reset "${role.agent_name}" to defaults`);
      await loadRoles();
    } catch (e) { toast.error(String(e)); }
  };

  const setField = (key: DraftKey, role: string, priority: number, field: keyof RoleAssignmentInput, val: string | number | null) => {
    setDraft((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || { role, provider_type: "ollama" as const, priority, workspace_server_id: scopeServerId ?? null }), [field]: val },
    }));
  };

  const handleSaveAssignments = async () => {
    const toSave = Object.values(draft).filter((r) =>
      r.provider_type === "ollama" ? r.ollama_server_id && r.model_name : r.agent_name,
    );
    if (toSave.length === 0) return;
    await updateRoleAssignments(toSave.map((r) => ({ ...r, workspace_server_id: scopeServerId ?? null })));
    toast.success("Role assignments saved");
    loadAssignments();
  };

  const handleDeleteAssignment = async (id: number) => {
    await deleteRoleAssignment(id);
    loadAssignments();
  };

  const getStyle = (name: string) => ROLE_STYLE[name] || { icon: Bot, border: "border-l-gray-500", text: "text-gray-400" };

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Cpu className="w-5 h-5 text-blue-400" />
          Roles
        </h1>
        <div className="flex items-center gap-2">
          <select
            className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            value={scopeServerId ?? ""}
            onChange={(e) => setScopeServerId(e.target.value ? parseInt(e.target.value) : undefined)}
          >
            <option value="">Global Defaults</option>
            {wsServers.map((ws) => <option key={ws.id} value={ws.id}>{ws.name}</option>)}
          </select>
          <button onClick={handleSaveAssignments} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors">
            <Save className="w-3.5 h-3.5" /> Save Assignments
          </button>
          <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors">
            <Plus className="w-3.5 h-3.5" /> Add Role
          </button>
        </div>
      </div>

      {error && <div className="bg-red-900/30 border border-red-800/50 rounded-xl p-4 mb-5 text-sm text-red-300">{error}</div>}

      {/* New Role Form */}
      {showForm && (
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 mb-4 backdrop-blur-sm">
          <h3 className="text-sm font-medium mb-3">New Role</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Name (unique ID)</label>
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. security-reviewer" className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Display Name</label>
              <input type="text" value={newDisplay} onChange={(e) => setNewDisplay(e.target.value)} placeholder="e.g. Security Reviewer" className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Description</label>
              <input type="text" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="What this role does" className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => { setShowForm(false); setNewName(""); setNewDisplay(""); setNewDesc(""); }} className="px-3 py-1.5 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">Cancel</button>
            <button onClick={handleCreate} disabled={!newName.trim() || !newDisplay.trim()} className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors">Create</button>
          </div>
        </div>
      )}

      {/* Role Cards */}
      <div className="space-y-3">
        {roles.map((role) => {
          const style = getStyle(role.agent_name);
          const RoleIcon = style.icon;
          const isExpanded = expanded === role.agent_name;
          const showPrompts = promptsOpen[role.agent_name] ?? false;
          const showOverrides = overridesOpen[role.agent_name] ?? false;

          return (
            <div key={role.agent_name} className={`bg-gray-900/40 border border-gray-800/60 border-l-2 ${style.border} rounded-xl backdrop-blur-sm`}>
              <button onClick={() => toggle(role.agent_name)} className="w-full flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <RoleIcon className={`w-4 h-4 ${style.text}`} />
                  <span className="text-sm font-medium">{role.display_name}</span>
                  {role.is_system && (
                    <span className="text-xs px-2 py-0.5 rounded-full text-blue-400 bg-blue-500/10 flex items-center gap-1">
                      <Shield className="w-3 h-3" /> System
                    </span>
                  )}
                  {role.phase_binding && <span className="text-xs px-2 py-0.5 rounded-full text-gray-400 bg-gray-700">{role.phase_binding}</span>}
                </div>
                {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
              </button>

              {isExpanded && (
                <div className="border-t border-gray-800/60 p-4 space-y-4">
                  <p className="text-xs text-gray-500">{role.description}</p>

                  {/* Inline Assignments */}
                  <div className="space-y-2">
                    <h4 className="text-xs font-medium text-gray-400 uppercase tracking-wider">Assignments</h4>
                    {[0, 1].map((priority) => {
                      const key = draftKey(role.agent_name, priority);
                      const existing = assignments.find((a) => a.role === role.agent_name && a.priority === priority);
                      return (
                        <AssignmentRow
                          key={key}
                          role={role.agent_name}
                          priority={priority}
                          draft={draft[key]}
                          existing={existing}
                          servers={ollamaServers}
                          onFieldChange={(field, val) => setField(key, role.agent_name, priority, field, val)}
                          onDelete={() => existing && handleDeleteAssignment(existing.id)}
                        />
                      );
                    })}
                  </div>

                  {/* Expandable: Prompts */}
                  <div className="border-t border-gray-800/40 pt-3">
                    <button onClick={() => setPromptsOpen((p) => ({ ...p, [role.agent_name]: !showPrompts }))} className="flex items-center gap-2 text-xs font-medium text-gray-400 hover:text-white transition-colors">
                      <ChevronRight className={`w-3.5 h-3.5 transition-transform ${showPrompts ? "rotate-90" : ""}`} />
                      Prompts & Parameters
                    </button>
                    {showPrompts && (
                      <div className="mt-3 space-y-3">
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">System Prompt</label>
                          <textarea defaultValue={role.system_prompt} onBlur={(e) => { if (e.target.value !== role.system_prompt) handleSaveField(role, "system_prompt", e.target.value); }} rows={5} className="w-full px-3 py-2 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-y" />
                        </div>
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">User Prompt Template</label>
                          <textarea defaultValue={role.user_prompt_template} onBlur={(e) => { if (e.target.value !== role.user_prompt_template) handleSaveField(role, "user_prompt_template", e.target.value); }} rows={8} className="w-full px-3 py-2 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-y" />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="block text-xs text-gray-400 mb-1">Temperature</label>
                            <input type="number" defaultValue={role.default_temperature} min={0} max={2} step={0.1} onBlur={(e) => { const v = parseFloat(e.target.value); if (!isNaN(v) && v !== role.default_temperature) handleSaveField(role, "default_temperature", v); }} className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-400 mb-1">Max Tokens</label>
                            <input type="number" defaultValue={role.default_num_predict} min={256} max={32768} step={256} onBlur={(e) => { const v = parseInt(e.target.value); if (!isNaN(v) && v !== role.default_num_predict) handleSaveField(role, "default_num_predict", v); }} className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Expandable: Per-Agent Overrides */}
                  <div className="border-t border-gray-800/40 pt-3">
                    <button onClick={() => setOverridesOpen((p) => ({ ...p, [role.agent_name]: !showOverrides }))} className="flex items-center gap-2 text-xs font-medium text-gray-400 hover:text-white transition-colors">
                      <ChevronRight className={`w-3.5 h-3.5 transition-transform ${showOverrides ? "rotate-90" : ""}`} />
                      Per-Agent Overrides
                    </button>
                    {showOverrides && (
                      <div className="mt-3">
                        <AgentOverridesSection configName={role.agent_name} />
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 justify-end pt-2 border-t border-gray-800/40">
                    {role.is_system && (
                      <button onClick={() => handleReset(role)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
                        <RotateCcw className="w-3.5 h-3.5" /> Reset to Default
                      </button>
                    )}
                    {!role.is_system && (
                      <button onClick={() => handleDelete(role)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-400 hover:text-red-300 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
                        <Trash2 className="w-3.5 h-3.5" /> Delete
                      </button>
                    )}
                  </div>
                  {saving === role.agent_name && <p className="text-xs text-blue-400">Saving...</p>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}