// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { Bot, Plus, Save, Trash2 } from "lucide-react";
import { updateProject } from "../../api";
import type { AutonomyConfig, ThresholdRule } from "../../types";

interface Props {
  projectId: string;
  initial: AutonomyConfig | null;
  onSaved: () => void;
}

const DEFAULT_CONFIG: AutonomyConfig = {
  execution_mode: "structured",
  plan_approval: "none",
  adaptive_max_files: 5,
  merge_mode: "pr_only",
  auto_merge_max_files: 3,
  auto_merge_require_green_ci: true,
  allow_agent_followups: false,
  max_followup_depth: 2,
  threshold_rules: [],
};

const EMPTY_RULE: ThresholdRule = { metric: "test_coverage", operator: "<", value: 70, task: "Improve test coverage for {project_id}" };

const EXECUTION_MODES = [
  { value: "structured", label: "Structured", desc: "8-phase pipeline (current default)" },
  { value: "autonomous", label: "Autonomous", desc: "Claude drives itself end-to-end" },
  { value: "hybrid", label: "Hybrid", desc: "Init phase + autonomous agent loop" },
  { value: "multi_agent", label: "Multi-Agent", desc: "Orchestrator spawns sub-agents" },
] as const;

const PLAN_APPROVALS = [
  { value: "none", label: "None — auto-proceed" },
  { value: "show_and_continue", label: "Show plan, continue after 5s" },
  { value: "require_approval", label: "Require human approval" },
  { value: "adaptive", label: "Adaptive (pause if large change)" },
] as const;

const MERGE_MODES = [
  { value: "pr_only", label: "PR only — human reviews" },
  { value: "auto_merge", label: "Auto-merge (if CI passes)" },
  { value: "risk_based", label: "Risk-based (small changes auto-merge)" },
] as const;

const METRICS = ["test_coverage", "lint_errors", "test_failures"] as const;
const OPERATORS = ["<", ">", "==", "<=", ">="] as const;

export default function AutonomyConfigPanel({ projectId, initial, onSaved }: Props) {
  const mergeWithDefaults = (cfg: AutonomyConfig | null | undefined): AutonomyConfig => ({
    ...DEFAULT_CONFIG,
    ...(cfg ?? {}),
    threshold_rules: cfg?.threshold_rules ?? [],
  });

  const [config, setConfig] = useState<AutonomyConfig>(() => mergeWithDefaults(initial));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setConfig(mergeWithDefaults(initial));
  }, [initial, projectId]);

  const set = <K extends keyof AutonomyConfig>(key: K, value: AutonomyConfig[K]) =>
    setConfig((c) => ({ ...c, [key]: value }));

  const addRule = () =>
    setConfig((c) => ({ ...c, threshold_rules: [...c.threshold_rules, { ...EMPTY_RULE }] }));

  const removeRule = (i: number) =>
    setConfig((c) => ({ ...c, threshold_rules: c.threshold_rules.filter((_, idx) => idx !== i) }));

  const updateRule = (i: number, patch: Partial<ThresholdRule>) =>
    setConfig((c) => ({
      ...c,
      threshold_rules: c.threshold_rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    }));

  const save = async () => {
    setSaving(true);
    try {
      await updateProject(projectId, { autonomy_config: config });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5 text-sm">
      <div className="flex items-center gap-2 text-purple-400 font-medium">
        <Bot className="w-4 h-4" />
        Autonomy Configuration
      </div>

      {/* Execution Mode */}
      <div>
        <label className="block text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">Execution Mode</label>
        <div className="grid grid-cols-2 gap-2">
          {EXECUTION_MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => set("execution_mode", m.value)}
              className={`text-left px-3 py-2.5 rounded-lg border transition-all ${
                config.execution_mode === m.value
                  ? "border-purple-500/60 bg-purple-900/20 text-white"
                  : "border-gray-700/50 bg-gray-800/30 text-gray-400 hover:border-gray-600 hover:text-gray-300"
              }`}
            >
              <div className="font-medium text-xs">{m.label}</div>
              <div className="text-xs text-gray-500 mt-0.5">{m.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Plan Approval — only shown for autonomous modes */}
      {config.execution_mode !== "structured" && (
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wide">Plan Approval Gate</label>
          <select
            value={config.plan_approval}
            onChange={(e) => set("plan_approval", e.target.value as AutonomyConfig["plan_approval"])}
            className="w-full bg-gray-800/60 border border-gray-700/50 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-1 focus:ring-purple-500/50"
          >
            {PLAN_APPROVALS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
          {config.plan_approval === "adaptive" && (
            <div className="mt-2 flex items-center gap-2">
              <label className="text-gray-400 text-xs">Pause if estimated files &gt;</label>
              <input
                type="number"
                min={1}
                max={50}
                value={config.adaptive_max_files}
                onChange={(e) => set("adaptive_max_files", Number(e.target.value))}
                className="w-16 bg-gray-800/60 border border-gray-700/50 rounded px-2 py-1 text-white text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              />
            </div>
          )}
        </div>
      )}

      {/* Merge Mode */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wide">Merge / PR Mode</label>
        <select
          value={config.merge_mode}
          onChange={(e) => set("merge_mode", e.target.value as AutonomyConfig["merge_mode"])}
          className="w-full bg-gray-800/60 border border-gray-700/50 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-1 focus:ring-purple-500/50"
        >
          {MERGE_MODES.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
        {config.merge_mode === "auto_merge" && (
          <div className="mt-2 space-y-1.5">
            <div className="flex items-center gap-2">
              <label className="text-gray-400 text-xs">Auto-merge max files</label>
              <input
                type="number"
                min={1}
                max={20}
                value={config.auto_merge_max_files}
                onChange={(e) => set("auto_merge_max_files", Number(e.target.value))}
                className="w-16 bg-gray-800/60 border border-gray-700/50 rounded px-2 py-1 text-white text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.auto_merge_require_green_ci}
                onChange={(e) => set("auto_merge_require_green_ci", e.target.checked)}
                className="accent-purple-500"
              />
              <span className="text-gray-400 text-xs">Require green CI before auto-merge</span>
            </label>
          </div>
        )}
      </div>

      {/* Follow-up Tasks */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wide">Agent Follow-up Tasks</label>
        <label className="flex items-center gap-2 cursor-pointer mb-2">
          <input
            type="checkbox"
            checked={config.allow_agent_followups}
            onChange={(e) => set("allow_agent_followups", e.target.checked)}
            className="accent-purple-500"
          />
          <span className="text-gray-300 text-xs">Allow agent to create follow-up task runs</span>
        </label>
        {config.allow_agent_followups && (
          <div className="flex items-center gap-2 ml-5">
            <label className="text-gray-400 text-xs">Max follow-up depth</label>
            <input
              type="number"
              min={1}
              max={5}
              value={config.max_followup_depth}
              onChange={(e) => set("max_followup_depth", Number(e.target.value))}
              className="w-16 bg-gray-800/60 border border-gray-700/50 rounded px-2 py-1 text-white text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50"
            />
          </div>
        )}
      </div>

      {/* Threshold Rules */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs text-gray-400 font-medium uppercase tracking-wide">Threshold Rules</label>
          <button
            onClick={addRule}
            className="text-xs text-purple-400 hover:text-purple-300 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-purple-900/20 transition-colors"
          >
            <Plus className="w-3 h-3" />
            Add rule
          </button>
        </div>
        {config.threshold_rules.length === 0 && (
          <p className="text-xs text-gray-600 italic">No rules — agent runs without auto-triggered follow-ups.</p>
        )}
        <div className="space-y-2">
          {config.threshold_rules.map((rule, i) => (
            <div key={i} className="flex items-center gap-2 bg-gray-800/40 border border-gray-700/40 rounded-lg px-3 py-2">
              <select
                value={rule.metric}
                onChange={(e) => updateRule(i, { metric: e.target.value })}
                className="bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1 text-white text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              >
                {METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <select
                value={rule.operator}
                onChange={(e) => updateRule(i, { operator: e.target.value as ThresholdRule["operator"] })}
                className="bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1 text-white text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50 w-14"
              >
                {OPERATORS.map((op) => <option key={op} value={op}>{op}</option>)}
              </select>
              <input
                type="number"
                value={rule.value}
                onChange={(e) => updateRule(i, { value: Number(e.target.value) })}
                className="w-16 bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1 text-white text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50"
              />
              <input
                type="text"
                value={rule.task}
                placeholder="Task description template"
                onChange={(e) => updateRule(i, { task: e.target.value })}
                className="flex-1 bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1 text-white text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50 placeholder-gray-600"
              />
              <button
                onClick={() => removeRule(i)}
                className="text-red-400 hover:text-red-300 p-1 rounded hover:bg-red-900/20 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
        {config.threshold_rules.length > 0 && (
          <p className="text-xs text-gray-600 mt-1.5">
            Templates: <code className="text-gray-500">{"{metric}"}</code>, <code className="text-gray-500">{"{value}"}</code>, <code className="text-gray-500">{"{project_id}"}</code>
          </p>
        )}
      </div>

      {/* Save */}
      <div className="flex justify-end pt-1">
        <button
          onClick={save}
          disabled={saving}
          className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-purple-500/40"
        >
          <Save className="w-3.5 h-3.5" />
          {saving ? "Saving…" : saved ? "Saved!" : "Save Autonomy Config"}
        </button>
      </div>
    </div>
  );
}
