// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type { PhaseConfig } from '../../types';
import { VISIBLE_AGENTS } from '../../types';

// Agents shown in the per-step picker. Sourced from the shared visible-agent
// allowlist (claude/codex/opencode) so it stays in sync with the rest of the
// UI. An empty value means "use the project/global default agent".
const AGENT_OPTIONS = Array.from(VISIBLE_AGENTS);

function getParamString(step: PhaseConfig, key: string): string {
  const v = step.params?.[key];
  return typeof v === 'string' ? v : '';
}

interface BodyProps {
  step: PhaseConfig;
  onParam: (key: string, value: unknown) => void;
  onChange: (next: PhaseConfig) => void;
}

interface LegacyBodyProps {
  step: PhaseConfig;
  onChange: (next: PhaseConfig) => void;
  legacyPhaseNames: string[];
}

const SUBSTITUTION_HELP = (
  <p className="mt-1 text-[10px] text-gray-500">
    Supports <code className="text-gray-400">{'{{run.title}}'}</code> and{' '}
    <code className="text-gray-400">{'{{steps.NAME.field}}'}</code>{' '}
    substitution.
  </p>
);

export function LegacyPhaseBody({
  step,
  onChange,
  legacyPhaseNames,
}: LegacyBodyProps) {
  return (
    <>
      <div>
        <label className="block text-xs text-gray-400 mb-1">Phase module</label>
        <select
          value={step.phase_name}
          onChange={(e) => onChange({ ...step, phase_name: e.target.value })}
          className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
        >
          {!legacyPhaseNames.includes(step.phase_name) && step.phase_name && (
            <option value={step.phase_name}>{step.phase_name} (custom)</option>
          )}
          {legacyPhaseNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="inline-flex items-center gap-2 text-xs text-gray-300">
          <input
            type="checkbox"
            checked={step.uses_agent ?? false}
            onChange={(e) =>
              onChange({ ...step, uses_agent: e.target.checked })
            }
            className="rounded border-gray-600"
          />
          Uses agent
        </label>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Agent mode</label>
          <select
            value={step.agent_mode ?? ''}
            onChange={(e) =>
              onChange({
                ...step,
                agent_mode:
                  (e.target.value as 'generate' | 'task' | '') || null,
              })
            }
            className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          >
            <option value="">Default</option>
            <option value="generate">Generate</option>
            <option value="task">Task</option>
          </select>
        </div>
      </div>
    </>
  );
}

export function BashBody({ step, onParam, onChange }: BodyProps) {
  return (
    <>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          Shell command
        </label>
        <textarea
          value={getParamString(step, 'command')}
          onChange={(e) => onParam('command', e.target.value)}
          rows={4}
          placeholder="echo hello"
          className="w-full px-2 py-1.5 text-xs bg-gray-800 border border-gray-700 rounded text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
        />
        {SUBSTITUTION_HELP}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Working directory
          </label>
          <input
            type="text"
            value={getParamString(step, 'working_dir')}
            onChange={(e) => onParam('working_dir', e.target.value)}
            placeholder="(workspace root)"
            className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Failure mode
          </label>
          <select
            value={step.failure_mode ?? 'fail'}
            onChange={(e) =>
              onChange({
                ...step,
                failure_mode: e.target.value as 'fail' | 'skip',
              })
            }
            className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          >
            <option value="fail">Fail run on non-zero exit</option>
            <option value="skip">Skip & continue on non-zero exit</option>
          </select>
        </div>
      </div>
    </>
  );
}

export function AgentBody({ step, onParam, onChange }: BodyProps) {
  const mode = getParamString(step, 'mode') || 'generate';
  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Mode</label>
          <select
            value={mode}
            onChange={(e) => onParam('mode', e.target.value)}
            className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          >
            <option value="generate">Generate</option>
            <option value="task">Task</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Agent</label>
          <select
            value={step.agent ?? ''}
            onChange={(e) =>
              onChange({ ...step, agent: e.target.value || null })
            }
            className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          >
            <option value="">Default (project/global)</option>
            {AGENT_OPTIONS.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">Prompt</label>
        <textarea
          value={getParamString(step, 'prompt')}
          onChange={(e) => onParam('prompt', e.target.value)}
          rows={6}
          placeholder="Describe what the agent should do…"
          className="w-full px-2 py-1.5 text-xs bg-gray-800 border border-gray-700 rounded text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
        />
        {SUBSTITUTION_HELP}
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">Failure mode</label>
        <select
          value={step.failure_mode ?? 'fail'}
          onChange={(e) =>
            onChange({
              ...step,
              failure_mode: e.target.value as 'fail' | 'skip',
            })
          }
          className="w-full sm:w-1/2 px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500/40"
        >
          <option value="fail">Fail run on error</option>
          <option value="skip">Skip & continue on error</option>
        </select>
      </div>
    </>
  );
}
