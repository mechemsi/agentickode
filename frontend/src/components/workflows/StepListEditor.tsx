// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { Plus } from 'lucide-react';
import type { PhaseConfig } from '../../types';
import StepEditor from './StepEditor';

interface StepListEditorProps {
  steps: PhaseConfig[];
  onChange: (next: PhaseConfig[]) => void;
  legacyPhaseNames: string[];
  agentNames: string[];
}

function makeDefaultStep(): PhaseConfig {
  return {
    phase_name: '',
    kind: 'bash',
    enabled: true,
    role: null,
    trigger_mode: 'auto',
    notify_source: false,
    timeout_seconds: null,
    params: { command: '' },
  };
}

export default function StepListEditor({
  steps,
  onChange,
  legacyPhaseNames,
  agentNames,
}: StepListEditorProps) {
  const updateStep = (idx: number, next: PhaseConfig) => {
    const copy = [...steps];
    copy[idx] = next;
    onChange(copy);
  };

  const removeStep = (idx: number) => {
    onChange(steps.filter((_, i) => i !== idx));
  };

  const moveStep = (idx: number, direction: 'up' | 'down') => {
    const targetIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (targetIdx < 0 || targetIdx >= steps.length) return;
    const copy = [...steps];
    [copy[idx], copy[targetIdx]] = [copy[targetIdx], copy[idx]];
    onChange(copy);
  };

  const addStep = () => {
    onChange([...steps, makeDefaultStep()]);
  };

  return (
    <div className="space-y-3">
      {steps.length === 0 && (
        <p className="text-xs text-gray-500 italic">
          No steps yet. Add one below to get started.
        </p>
      )}
      {steps.map((step, idx) => (
        <StepEditor
          key={idx}
          step={step}
          onChange={(next) => updateStep(idx, next)}
          onRemove={() => removeStep(idx)}
          onMoveUp={() => moveStep(idx, 'up')}
          onMoveDown={() => moveStep(idx, 'down')}
          canMoveUp={idx > 0}
          canMoveDown={idx < steps.length - 1}
          legacyPhaseNames={legacyPhaseNames}
          agentNames={agentNames}
        />
      ))}
      <button
        type="button"
        onClick={addStep}
        className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm text-gray-300 hover:text-white bg-gray-800/40 hover:bg-gray-800 border border-dashed border-gray-700 hover:border-gray-600 rounded-lg transition-colors"
      >
        <Plus className="w-3.5 h-3.5" />
        Add step
      </button>
    </div>
  );
}
