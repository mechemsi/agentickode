// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  Bot,
  ChevronDown,
  ChevronUp,
  Settings,
  Terminal,
  Trash2,
} from 'lucide-react';
import type { PhaseConfig, StepKind } from '../../types';
import { AgentBody, BashBody, LegacyPhaseBody } from './stepBodies';

interface StepEditorProps {
  step: PhaseConfig;
  onChange: (next: PhaseConfig) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
  /** Phase module names from GET /step-kinds → kind=legacy_phase → values */
  legacyPhaseNames: string[];
  /** Agent names from getAgents() for the agent_override dropdown */
  agentNames: string[];
}

const KIND_OPTIONS: { value: StepKind; label: string }[] = [
  { value: 'legacy_phase', label: 'Legacy phase' },
  { value: 'bash', label: 'Bash' },
  { value: 'agent', label: 'Agent' },
];

const KIND_ICONS: Record<StepKind, React.ReactNode> = {
  legacy_phase: <Settings className="w-3.5 h-3.5 text-gray-400" />,
  bash: <Terminal className="w-3.5 h-3.5 text-emerald-400" />,
  agent: <Bot className="w-3.5 h-3.5 text-blue-400" />,
};

function getKind(step: PhaseConfig): StepKind {
  return (step.kind ?? 'legacy_phase') as StepKind;
}

export default function StepEditor({
  step,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
  canMoveUp,
  canMoveDown,
  legacyPhaseNames,
  agentNames,
}: StepEditorProps) {
  const [rulesOpen, setRulesOpen] = useState(false);
  const kind = getKind(step);

  const setKind = (nextKind: StepKind) => {
    const nextParams: Record<string, unknown> = { ...(step.params ?? {}) };
    if (nextKind === 'bash') {
      if (typeof nextParams.command !== 'string') nextParams.command = '';
    } else if (nextKind === 'agent') {
      if (typeof nextParams.prompt !== 'string') nextParams.prompt = '';
      if (typeof nextParams.mode !== 'string') nextParams.mode = 'generate';
    }
    onChange({ ...step, kind: nextKind, params: nextParams });
  };

  const setParam = (key: string, value: unknown) => {
    onChange({ ...step, params: { ...(step.params ?? {}), [key]: value } });
  };

  return (
    <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl backdrop-blur-sm">
      {/* Header row */}
      <div className="flex items-center gap-2 p-3 border-b border-gray-800/60">
        <span className="shrink-0">{KIND_ICONS[kind]}</span>
        <input
          type="text"
          value={step.phase_name}
          onChange={(e) => onChange({ ...step, phase_name: e.target.value })}
          placeholder="step-name"
          className="flex-1 px-2 py-1 text-sm bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as StepKind)}
          className="px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          title="Step kind"
        >
          {KIND_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <div className="flex gap-0.5">
          <button
            type="button"
            onClick={onMoveUp}
            disabled={!canMoveUp}
            className="p-1 text-gray-500 hover:text-white disabled:opacity-30 disabled:hover:text-gray-500"
            title="Move up"
          >
            <ArrowUp className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            disabled={!canMoveDown}
            className="p-1 text-gray-500 hover:text-white disabled:opacity-30 disabled:hover:text-gray-500"
            title="Move down"
          >
            <ArrowDown className="w-3.5 h-3.5" />
          </button>
        </div>
        <button
          type="button"
          onClick={onRemove}
          className="p-1 text-gray-500 hover:text-red-400"
          title="Remove step"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Kind-specific body */}
      <div className="p-3 space-y-3">
        {kind === 'legacy_phase' && (
          <LegacyPhaseBody
            step={step}
            onChange={onChange}
            legacyPhaseNames={legacyPhaseNames}
            agentNames={agentNames}
          />
        )}

        {kind === 'bash' && (
          <BashBody step={step} onParam={setParam} onChange={onChange} />
        )}

        {kind === 'agent' && (
          <AgentBody
            step={step}
            onParam={setParam}
            onChange={onChange}
            agentNames={agentNames}
          />
        )}
      </div>

      {/* Common rules (collapsible) */}
      <div className="border-t border-gray-800/60">
        <button
          type="button"
          onClick={() => setRulesOpen((open) => !open)}
          className="w-full flex items-center justify-between px-3 py-2 text-xs text-gray-400 hover:text-gray-200"
        >
          <span className="flex items-center gap-1.5">
            <Settings className="w-3.5 h-3.5" />
            Rules
          </span>
          {rulesOpen ? (
            <ChevronUp className="w-3.5 h-3.5" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" />
          )}
        </button>
        {rulesOpen && (
          <div className="px-3 pb-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="inline-flex items-center gap-2 text-xs text-gray-300">
              <input
                type="checkbox"
                checked={step.enabled}
                onChange={(e) => onChange({ ...step, enabled: e.target.checked })}
                className="rounded border-gray-600"
              />
              Enabled
            </label>
            <label className="inline-flex items-center gap-2 text-xs text-gray-300">
              <input
                type="checkbox"
                checked={step.notify_source ?? false}
                onChange={(e) =>
                  onChange({ ...step, notify_source: e.target.checked })
                }
                className="rounded border-gray-600"
              />
              Notify task source on completion
            </label>
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Trigger mode
              </label>
              <select
                value={step.trigger_mode || 'auto'}
                onChange={(e) =>
                  onChange({ ...step, trigger_mode: e.target.value })
                }
                className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
              >
                <option value="auto">Auto</option>
                <option value="wait_for_trigger">Wait for trigger</option>
                <option value="wait_for_approval">Wait for approval</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Timeout (seconds)
              </label>
              <input
                type="number"
                value={step.timeout_seconds ?? ''}
                onChange={(e) => {
                  const raw = e.target.value.trim();
                  const next = raw ? parseInt(raw, 10) || null : null;
                  onChange({ ...step, timeout_seconds: next });
                }}
                placeholder="default"
                className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
