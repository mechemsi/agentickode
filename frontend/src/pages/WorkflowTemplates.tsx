// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronUp,
  GitBranch,
  Plus,
  Settings,
  Shield,
  Trash2,
} from "lucide-react";
import {
  getWorkflowTemplates,
  getAgents,
  getRoleAssignments,
  getPhases,
  createWorkflowTemplate,
  updateWorkflowTemplate,
  deleteWorkflowTemplate,
} from "../api";
import type { AgentSettings, PhaseConfig, PhaseInfo, RoleAssignment, WorkflowTemplate } from "../types";
import { useConfirm } from "../components/shared/ConfirmDialog";
import { useToast } from "../components/shared/Toast";
import { KVEditor, parseKV, kvToObject } from "../components/shared/KVEditor";
import type { KVEntry } from "../components/shared/KVEditor";

const getEffectiveMode = (
  phase: PhaseConfig,
  phaseModes: Record<string, "generate" | "task">,
): "generate" | "task" => {
  if (phase.agent_mode === "generate" || phase.agent_mode === "task") return phase.agent_mode;
  return phaseModes[phase.phase_name] ?? "generate";
};

const MODE_COMMANDS: Record<string, { key: string; label: string }[]> = {
  generate: [
    { key: "generate", label: "One-shot generate" },
    { key: "generate_session_start", label: "Session start" },
    { key: "generate_continue", label: "Session continue" },
  ],
  task: [
    { key: "task", label: "One-shot task" },
    { key: "task_session_start", label: "Session start" },
    { key: "task_continue", label: "Session continue" },
  ],
};

/** Mini command-flow display showing which command template keys will be used. */
function CommandFlowDisplay({
  phase,
  agentDefaults,
  phaseModes,
}: {
  phase: PhaseConfig;
  agentDefaults: AgentSettings | null;
  phaseModes: Record<string, "generate" | "task">;
}) {
  const mode = getEffectiveMode(phase, phaseModes);
  const commands = MODE_COMMANDS[mode] ?? [];
  const agentCmds = agentDefaults?.command_templates ?? {};
  const phaseCmds = phase.command_templates ?? {};

  return (
    <div className="mt-3">
      <label className="block text-xs text-gray-400 mb-1.5">
        Command Flow <span className="text-gray-600 font-normal">— mode: <span className="text-blue-400">{mode}</span></span>
      </label>
      <div className="space-y-1">
        {commands.map(({ key }) => {
          const isOverridden = key in phaseCmds;
          const resolved = phaseCmds[key] ?? agentCmds[key as keyof typeof agentCmds] ?? null;
          const isSession = key.includes("session") || key.includes("continue");
          const supportsSession = agentDefaults?.supports_session ?? false;
          return (
            <div
              key={key}
              className={`flex items-start gap-2 px-2 py-1 rounded text-[11px] font-mono ${
                isSession && !supportsSession ? "opacity-40" : ""
              }`}
            >
              <span className="text-gray-500 shrink-0 w-40 truncate" title={key}>
                {key}
              </span>
              <span className="text-gray-400 flex-1 truncate" title={resolved ? String(resolved) : "(using default)"}>
                {resolved ? String(resolved) : <span className="text-gray-600 italic">(using default)</span>}
              </span>
              {isOverridden && (
                <span className="text-yellow-400 text-[9px] px-1 py-0.5 bg-yellow-500/10 rounded shrink-0">
                  overridden
                </span>
              )}
              {isSession && !supportsSession && (
                <span className="text-gray-600 text-[9px] shrink-0">no sessions</span>
              )}
            </div>
          );
        })}
        {/* Always show check */}
        <div className="flex items-start gap-2 px-2 py-1 rounded text-[11px] font-mono">
          <span className="text-gray-500 shrink-0 w-40 truncate">check</span>
          <span className="text-gray-400 flex-1 truncate" title={String(phaseCmds["check"] ?? agentCmds["check" as keyof typeof agentCmds] ?? "")}>
            {phaseCmds["check"] ?? agentCmds["check" as keyof typeof agentCmds] ?? <span className="text-gray-600 italic">(using default)</span>}
          </span>
          {("check" in phaseCmds) && (
            <span className="text-yellow-400 text-[9px] px-1 py-0.5 bg-yellow-500/10 rounded shrink-0">
              overridden
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/** Read-only list of key→value pairs shown as inherited defaults. */
function InheritedKV({ entries, label }: { entries: [string, string][]; label: string }) {
  if (!entries.length) return null;
  return (
    <div className="mt-1 space-y-0.5">
      <span className="text-[10px] text-gray-500">{label}</span>
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2 items-center opacity-50">
          <span className="flex-1 px-2 py-0.5 text-[11px] bg-gray-900/60 border border-gray-800 rounded text-gray-400 font-mono truncate">
            {k}
          </span>
          <span className="flex-1 px-2 py-0.5 text-[11px] bg-gray-900/60 border border-gray-800 rounded text-gray-400 font-mono truncate">
            {String(v)}
          </span>
        </div>
      ))}
    </div>
  );
}

function PhaseAdvancedConfig({
  phase,
  onSave,
  agentDefaults,
  phaseModes,
}: {
  phase: PhaseConfig;
  onSave: (updates: Partial<PhaseConfig>) => void;
  agentDefaults: AgentSettings | null;
  phaseModes: Record<string, "generate" | "task">;
}) {
  const [timeout, setTimeout] = useState<string>(
    phase.timeout_seconds != null ? String(phase.timeout_seconds) : "",
  );
  const [cliFlags, setCliFlags] = useState<KVEntry[]>(
    parseKV(phase.cli_flags as Record<string, string>),
  );
  const [envVars, setEnvVars] = useState<KVEntry[]>(
    parseKV(phase.environment_vars as Record<string, string>),
  );
  const [cmdTemplates, setCmdTemplates] = useState<KVEntry[]>(
    parseKV(phase.command_templates as Record<string, string>),
  );
  const isCodingPhase = phase.phase_name === "coding";
  const [executionMode, setExecutionMode] = useState<"agent_default" | "consolidated" | "batch" | "separate">(
    phase.params?.consolidated === true
      ? "consolidated"
      : phase.params?.consolidated === false
        ? (phase.params?.subtask_mode === "separate" ? "separate" : "batch")
        : "agent_default",
  );

  const handleSave = () => {
    const updates: Partial<PhaseConfig> = {};
    const t = timeout.trim();
    updates.timeout_seconds = t ? parseInt(t, 10) || null : null;

    const flags = kvToObject(cliFlags);
    updates.cli_flags = Object.keys(flags).length ? flags : null;

    const env = kvToObject(envVars);
    updates.environment_vars = Object.keys(env).length ? env : null;

    const cmd = kvToObject(cmdTemplates);
    updates.command_templates = Object.keys(cmd).length ? cmd : null;

    if (isCodingPhase) {
      const existingParams = { ...(phase.params || {}) };
      if (executionMode === "agent_default") {
        delete existingParams.consolidated;
        delete existingParams.subtask_mode;
      } else if (executionMode === "consolidated") {
        existingParams.consolidated = true;
        delete existingParams.subtask_mode;
      } else {
        existingParams.consolidated = false;
        existingParams.subtask_mode = executionMode;
      }
      updates.params = existingParams;
    }

    onSave(updates);
  };

  // Build inherited entries from agent settings
  const inheritedCmds: [string, string][] = agentDefaults?.command_templates
    ? Object.entries(agentDefaults.command_templates).map(([k, v]) => [k, String(v)])
    : [];
  const inheritedFlags: [string, string][] = agentDefaults?.cli_flags
    ? Object.entries(agentDefaults.cli_flags).map(([k, v]) => [k, String(v)])
    : [];
  const inheritedEnv: [string, string][] = agentDefaults?.environment_vars
    ? Object.entries(agentDefaults.environment_vars).map(([k, v]) => [k, String(v)])
    : [];

  return (
    <div className="border-t border-gray-700/40 px-3 pb-3 pt-2 space-y-3">
      {agentDefaults && (
        <p className="text-[10px] text-gray-500">
          Inheriting from agent: <span className="text-gray-400 font-medium">{agentDefaults.display_name}</span>
          {agentDefaults.default_timeout ? ` (timeout: ${agentDefaults.default_timeout}s)` : ""}
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Timeout (seconds)
          </label>
          <input
            type="number"
            value={timeout}
            onChange={(e) => setTimeout(e.target.value)}
            placeholder={agentDefaults?.default_timeout ? `${agentDefaults.default_timeout} (from agent)` : "No default"}
            className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          />
        </div>
        {isCodingPhase && (
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Execution Mode
            </label>
            <select
              value={executionMode}
              onChange={(e) => setExecutionMode(e.target.value as typeof executionMode)}
              className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
            >
              <option value="agent_default">Agent default{agentDefaults?.consolidated_default != null ? ` (${agentDefaults.consolidated_default ? "consolidated" : "multi-step"})` : ""}</option>
              <option value="consolidated">Consolidated — single invocation</option>
              <option value="batch">Batch — all subtasks in one prompt</option>
              <option value="separate">Separate — one call per subtask</option>
            </select>
          </div>
        )}
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1">
          CLI Flags <span className="text-gray-600 font-normal">— merged over agent defaults</span>
        </label>
        <KVEditor
          entries={cliFlags}
          onChange={setCliFlags}
          keyPlaceholder="--flag"
          valuePlaceholder="value"
        />
        <InheritedKV entries={inheritedFlags} label="Inherited from agent:" />
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1">
          Environment Variables <span className="text-gray-600 font-normal">— merged over agent defaults</span>
        </label>
        <KVEditor
          entries={envVars}
          onChange={setEnvVars}
          maskValues
          keyPlaceholder="VAR_NAME"
          valuePlaceholder="value"
        />
        <InheritedKV entries={inheritedEnv} label="Inherited from agent:" />
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1">
          Command Templates <span className="text-gray-600 font-normal">— override agent commands</span>
        </label>
        <KVEditor
          entries={cmdTemplates}
          onChange={setCmdTemplates}
          keyPlaceholder="command_name"
          valuePlaceholder="template string"
        />
        <InheritedKV entries={inheritedCmds} label="Inherited from agent:" />
      </div>

      <CommandFlowDisplay phase={phase} agentDefaults={agentDefaults} phaseModes={phaseModes} />

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
        >
          Save Overrides
        </button>
      </div>
    </div>
  );
}

export default function WorkflowTemplates() {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [agentSettings, setAgentSettings] = useState<AgentSettings[]>([]);
  const [roleAssignments, setRoleAssignments] = useState<RoleAssignment[]>([]);
  const [availablePhases, setAvailablePhases] = useState<PhaseInfo[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null); // "templateId-phaseIdx"
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();
  const toast = useToast();

  // Derived: phase name → default agent mode (from API)
  const phaseModes: Record<string, "generate" | "task"> = {};
  for (const p of availablePhases) {
    if (p.default_agent_mode) phaseModes[p.name] = p.default_agent_mode;
  }

  // New template form
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  const load = async () => {
    try {
      const [t, r, as_, ph] = await Promise.all([
        getWorkflowTemplates(),
        getRoleAssignments(),
        getAgents(),
        getPhases(),
      ]);
      setTemplates(t);
      setRoleAssignments(r);
      setAgentSettings(as_);
      setAvailablePhases(ph);
      const dbRoles = r.map((ra: RoleAssignment) => ra.role);
      const defaultRoles = ph
        .filter((p: PhaseInfo) => p.default_role)
        .map((p: PhaseInfo) => p.default_role!);
      setRoles([...new Set([...defaultRoles, ...dbRoles])].sort());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const toggle = (id: number) => setExpanded(expanded === id ? null : id);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const defaultPhases: PhaseConfig[] = availablePhases.map((p) => ({
        phase_name: p.name,
        enabled: true,
        role: null,
        uses_agent: p.default_role ? true : null,
        trigger_mode: p.name === "approval" ? "wait_for_approval" : "auto",
        notify_source: false,
        timeout_seconds: null,
        params: {},
      }));
      await createWorkflowTemplate({
        name: newName.trim(),
        description: newDesc.trim(),
        phases: defaultPhases,
      });
      toast.success(`Template "${newName}" created`);
      setNewName("");
      setNewDesc("");
      setShowForm(false);
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleDelete = async (t: WorkflowTemplate) => {
    const ok = await confirm({
      title: "Delete Workflow",
      message: `Delete workflow "${t.name}"? This cannot be undone.`,
      confirmLabel: "Delete",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await deleteWorkflowTemplate(t.id);
      toast.success(`Workflow "${t.name}" deleted`);
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleTogglePhase = async (t: WorkflowTemplate, idx: number) => {
    const phases = [...t.phases];
    phases[idx] = { ...phases[idx], enabled: !phases[idx].enabled };
    try {
      await updateWorkflowTemplate(t.id, { phases });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleRoleChange = async (
    t: WorkflowTemplate,
    idx: number,
    value: string,
  ) => {
    const phases = [...t.phases];
    phases[idx] = { ...phases[idx], role: value || null };
    try {
      await updateWorkflowTemplate(t.id, { phases });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleTriggerMode = async (
    t: WorkflowTemplate,
    idx: number,
    value: string,
  ) => {
    const phases = [...t.phases];
    phases[idx] = { ...phases[idx], trigger_mode: value };
    try {
      await updateWorkflowTemplate(t.id, { phases });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleNotifySource = async (
    t: WorkflowTemplate,
    idx: number,
  ) => {
    const phases = [...t.phases];
    phases[idx] = { ...phases[idx], notify_source: !phases[idx].notify_source };
    try {
      await updateWorkflowTemplate(t.id, { phases });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handlePhaseAdvancedSave = async (
    t: WorkflowTemplate,
    idx: number,
    updates: Partial<PhaseConfig>,
  ) => {
    const phases = [...t.phases];
    phases[idx] = { ...phases[idx], ...updates };
    try {
      await updateWorkflowTemplate(t.id, { phases });
      await load();
      toast.success("Phase settings saved");
    } catch (e) {
      toast.error(String(e));
    }
  };

  /** Resolve which AgentSettings applies to a phase via role → agent mapping. */
  const resolveAgentDefaults = (phase: PhaseConfig): AgentSettings | null => {
    const phaseInfo = availablePhases.find((p) => p.name === phase.phase_name);
    const role = phase.role || phaseInfo?.default_role;
    if (!role) return null;
    const ra = roleAssignments.find((r) => r.role === role);
    const agentName = ra?.agent_name ?? null;
    if (!agentName) return null;
    return agentSettings.find((s) => s.agent_name === agentName) ?? null;
  };

  const isAgentPhase = (phase: PhaseConfig): boolean => {
    if (phase.uses_agent != null) return phase.uses_agent;
    const phaseInfo = availablePhases.find((p) => p.name === phase.phase_name);
    return !!phaseInfo?.default_role;
  };

  const handleAgentModeChange = async (t: WorkflowTemplate, idx: number, mode: string) => {
    const phases = [...t.phases];
    phases[idx] = { ...phases[idx], agent_mode: mode === "" ? null : mode as "generate" | "task" };
    try {
      await updateWorkflowTemplate(t.id, { phases });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleUsesAgentToggle = async (t: WorkflowTemplate, idx: number) => {
    const phases = [...t.phases];
    const current = isAgentPhase(phases[idx]);
    phases[idx] = { ...phases[idx], uses_agent: !current };
    try {
      await updateWorkflowTemplate(t.id, { phases });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const togglePhaseAdvanced = (templateId: number, phaseIdx: number) => {
    const key = `${templateId}-${phaseIdx}`;
    setExpandedPhase(expandedPhase === key ? null : key);
  };

  const handleMovePhase = async (
    t: WorkflowTemplate,
    idx: number,
    direction: "up" | "down",
  ) => {
    const phases = [...t.phases];
    const newIdx = direction === "up" ? idx - 1 : idx + 1;
    if (newIdx < 0 || newIdx >= phases.length) return;
    [phases[idx], phases[newIdx]] = [phases[newIdx], phases[idx]];
    try {
      await updateWorkflowTemplate(t.id, { phases });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleLabelRuleChange = async (
    t: WorkflowTemplate,
    ruleIdx: number,
    field: "match_all" | "match_any",
    value: string,
  ) => {
    const rules = [...(t.label_rules || [])];
    rules[ruleIdx] = {
      ...rules[ruleIdx],
      [field]: value
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      await updateWorkflowTemplate(t.id, { label_rules: rules });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleAddRule = async (t: WorkflowTemplate) => {
    const rules = [...(t.label_rules || []), { match_all: [], match_any: [] }];
    try {
      await updateWorkflowTemplate(t.id, { label_rules: rules });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleRemoveRule = async (t: WorkflowTemplate, ruleIdx: number) => {
    const rules = [...(t.label_rules || [])];
    rules.splice(ruleIdx, 1);
    try {
      await updateWorkflowTemplate(t.id, { label_rules: rules });
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-blue-400" />
          Workflow Templates
        </h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          Add Workflow
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-800/50 rounded-xl p-4 mb-5 text-sm text-red-300">
          {error}
        </div>
      )}

      {showForm && (
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 mb-4 backdrop-blur-sm">
          <h3 className="text-sm font-medium mb-3">New Workflow Template</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Name</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. quick-fix"
                className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Description
              </label>
              <input
                type="text"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="What this workflow does"
                className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => {
                setShowForm(false);
                setNewName("");
                setNewDesc("");
              }}
              className="px-3 py-1.5 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={!newName.trim()}
              className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              Create
            </button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {templates.map((t) => (
          <div
            key={t.id}
            className="bg-gray-900/40 border border-gray-800/60 rounded-xl backdrop-blur-sm"
          >
            <button
              onClick={() => toggle(t.id)}
              className="w-full flex items-center justify-between p-4"
            >
              <div className="flex items-center gap-3">
                <GitBranch className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-medium">{t.name}</span>
                {t.is_default && (
                  <span className="text-xs px-2 py-0.5 rounded-full text-blue-400 bg-blue-500/10 flex items-center gap-1">
                    <Shield className="w-3 h-3" /> Default
                  </span>
                )}
                {t.is_system && !t.is_default && (
                  <span className="text-xs px-2 py-0.5 rounded-full text-purple-400 bg-purple-500/10 flex items-center gap-1">
                    <Shield className="w-3 h-3" /> System
                  </span>
                )}
                <span className="text-xs text-gray-500">
                  {t.phases.filter((p) => p.enabled).length}/{t.phases.length}{" "}
                  phases
                </span>
              </div>
              {expanded === t.id ? (
                <ChevronUp className="w-4 h-4 text-gray-500" />
              ) : (
                <ChevronDown className="w-4 h-4 text-gray-500" />
              )}
            </button>

            {expanded === t.id && (
              <div className="border-t border-gray-800/60 p-4 space-y-4">
                <p className="text-xs text-gray-500">{t.description}</p>

                {/* Label Rules */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs text-gray-400 font-medium">
                      Label Rules
                    </label>
                    <button
                      onClick={() => handleAddRule(t)}
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      + Add Rule
                    </button>
                  </div>
                  {(t.label_rules || []).length === 0 && (
                    <p className="text-xs text-gray-600">
                      No label rules — this template must be the default or
                      won't match.
                    </p>
                  )}
                  {(t.label_rules || []).map((rule, ri) => (
                    <div
                      key={ri}
                      className="bg-gray-800/50 rounded-lg p-3 mb-2 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-500">
                          Rule {ri + 1}
                        </span>
                        <button
                          onClick={() => handleRemoveRule(t, ri)}
                          className="text-xs text-red-400 hover:text-red-300"
                        >
                          Remove
                        </button>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-xs text-gray-500 mb-1">
                            Match ALL (comma-separated)
                          </label>
                          <input
                            type="text"
                            defaultValue={(rule.match_all || []).join(", ")}
                            onBlur={(e) =>
                              handleLabelRuleChange(
                                t,
                                ri,
                                "match_all",
                                e.target.value,
                              )
                            }
                            className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-gray-500 mb-1">
                            Match ANY (comma-separated)
                          </label>
                          <input
                            type="text"
                            defaultValue={(rule.match_any || []).join(", ")}
                            onBlur={(e) =>
                              handleLabelRuleChange(
                                t,
                                ri,
                                "match_any",
                                e.target.value,
                              )
                            }
                            className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Phases */}
                <div>
                  <label className="block text-xs text-gray-400 font-medium mb-2">
                    Phases
                  </label>
                  <div className="space-y-1">
                    {t.phases.map((phase, pi) => {
                      const advKey = `${t.id}-${pi}`;
                      const hasOverrides = !!(phase.cli_flags && Object.keys(phase.cli_flags).length)
                        || !!(phase.environment_vars && Object.keys(phase.environment_vars).length)
                        || !!(phase.command_templates && Object.keys(phase.command_templates).length)
                        || !!(phase.timeout_seconds);
                      return (
                      <div key={pi} className={`rounded-lg ${phase.enabled ? "bg-gray-800/50" : "bg-gray-800/20"}`}>
                        <div className="flex items-center gap-3 px-3 py-2">
                        <input
                          type="checkbox"
                          checked={phase.enabled}
                          onChange={() => handleTogglePhase(t, pi)}
                          className="rounded border-gray-600"
                        />
                        <span
                          className={`text-sm flex-1 ${phase.enabled ? "text-white" : "text-gray-600"}`}
                        >
                          {phase.phase_name}
                        </span>
                        <label className="inline-flex items-center gap-1 text-xs text-gray-500 cursor-pointer" title="Use AI agent for this phase">
                          <input
                            type="checkbox"
                            checked={isAgentPhase(phase)}
                            onChange={() => handleUsesAgentToggle(t, pi)}
                            className="rounded border-gray-600"
                          />
                          Agent
                        </label>
                        {isAgentPhase(phase) && (
                          <select
                            value={phase.agent_mode || ""}
                            onChange={(e) => handleAgentModeChange(t, pi, e.target.value)}
                            className="px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-400 focus:outline-none"
                            title="Agent execution mode"
                          >
                            <option value="">Default ({phaseModes[phase.phase_name] ?? "generate"})</option>
                            <option value="generate">Generate</option>
                            <option value="task">Task</option>
                          </select>
                        )}
                        {isAgentPhase(phase) && (
                          <select
                            value={phase.role || ""}
                            onChange={(e) =>
                              handleRoleChange(t, pi, e.target.value)
                            }
                            className="px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-400 focus:outline-none"
                          >
                            <option value="">Default role</option>
                            {roles.map((r) => (
                              <option key={r} value={r}>
                                {r}
                              </option>
                            ))}
                          </select>
                        )}
                        <select
                          value={phase.trigger_mode || "auto"}
                          onChange={(e) =>
                            handleTriggerMode(t, pi, e.target.value)
                          }
                          className="px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-400 focus:outline-none"
                        >
                          <option value="auto">Auto</option>
                          <option value="wait_for_trigger">Wait for Trigger</option>
                          <option value="wait_for_approval">Wait for Approval</option>
                        </select>
                        <label className="inline-flex items-center gap-1 text-xs text-gray-500 cursor-pointer" title="Notify task source on completion">
                          <input
                            type="checkbox"
                            checked={phase.notify_source ?? false}
                            onChange={() => handleNotifySource(t, pi)}
                            className="rounded border-gray-600"
                          />
                          Notify
                        </label>
                        {isAgentPhase(phase) && (
                          <button
                            onClick={() => togglePhaseAdvanced(t.id, pi)}
                            className={`p-1 transition-colors ${
                              expandedPhase === advKey
                                ? "text-blue-400"
                                : hasOverrides
                                  ? "text-yellow-400 hover:text-yellow-300"
                                  : "text-gray-500 hover:text-white"
                            }`}
                            title="Phase command overrides"
                          >
                            <Settings className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <div className="flex gap-0.5">
                          <button
                            onClick={() => handleMovePhase(t, pi, "up")}
                            disabled={pi === 0}
                            className="p-1 text-gray-500 hover:text-white disabled:opacity-30"
                          >
                            <ArrowUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleMovePhase(t, pi, "down")}
                            disabled={pi === t.phases.length - 1}
                            className="p-1 text-gray-500 hover:text-white disabled:opacity-30"
                          >
                            <ArrowDown className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        </div>
                        {expandedPhase === advKey && isAgentPhase(phase) && (
                          <PhaseAdvancedConfig
                            phase={phase}
                            onSave={(updates) => handlePhaseAdvancedSave(t, pi, updates)}
                            agentDefaults={resolveAgentDefaults(phase)}
                            phaseModes={phaseModes}
                          />
                        )}
                      </div>
                      );
                    })}
                  </div>
                </div>

                {!t.is_default && !t.is_system && (
                  <div className="flex justify-end pt-2 border-t border-gray-800/40">
                    <button
                      onClick={() => handleDelete(t)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-400 hover:text-red-300 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Delete
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}