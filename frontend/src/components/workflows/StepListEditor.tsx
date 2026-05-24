// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import type { PhaseConfig } from '../../types';
import StepEditor from './StepEditor';

interface StepListEditorProps {
  steps: PhaseConfig[];
  onChange: (next: PhaseConfig[]) => void;
  legacyPhaseNames: string[];
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

// Stable per-step React keys so editor sub-state (e.g. the Rules collapse)
// follows the row across reorders instead of sticking to its index slot.
// IDs are tracked in component state and mutated in lockstep with the
// steps array — they're not derived from PhaseConfig because steps may
// share names (or have empty names during edits).
let _nextStepKeyId = 0;
const genStepKey = () =>
  `step-${++_nextStepKeyId}-${Math.random().toString(36).slice(2, 8)}`;

export default function StepListEditor({
  steps,
  onChange,
  legacyPhaseNames,
}: StepListEditorProps) {
  const [keys, setKeys] = useState<string[]>(() => steps.map(genStepKey));
  const prevLenRef = useRef(steps.length);

  // If the parent swaps the whole `steps` array (e.g. switching templates),
  // resync key length without losing identities for the slice that overlaps.
  useEffect(() => {
    if (steps.length === prevLenRef.current && steps.length === keys.length) {
      return;
    }
    setKeys((prev) => {
      if (prev.length === steps.length) return prev;
      if (prev.length < steps.length) {
        const extra = Array.from(
          { length: steps.length - prev.length },
          genStepKey,
        );
        return [...prev, ...extra];
      }
      return prev.slice(0, steps.length);
    });
    prevLenRef.current = steps.length;
  }, [steps.length, keys.length]);

  const updateStep = (idx: number, next: PhaseConfig) => {
    const copy = [...steps];
    copy[idx] = next;
    onChange(copy);
  };

  const removeStep = (idx: number) => {
    onChange(steps.filter((_, i) => i !== idx));
    setKeys(keys.filter((_, i) => i !== idx));
    prevLenRef.current = steps.length - 1;
  };

  const moveStep = (idx: number, direction: 'up' | 'down') => {
    const targetIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (targetIdx < 0 || targetIdx >= steps.length) return;
    const stepsCopy = [...steps];
    const keysCopy = [...keys];
    [stepsCopy[idx], stepsCopy[targetIdx]] = [stepsCopy[targetIdx], stepsCopy[idx]];
    [keysCopy[idx], keysCopy[targetIdx]] = [keysCopy[targetIdx], keysCopy[idx]];
    onChange(stepsCopy);
    setKeys(keysCopy);
  };

  const addStep = () => {
    onChange([...steps, makeDefaultStep()]);
    setKeys([...keys, genStepKey()]);
    prevLenRef.current = steps.length + 1;
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
          key={keys[idx] ?? `fallback-${idx}`}
          step={step}
          onChange={(next) => updateStep(idx, next)}
          onRemove={() => removeStep(idx)}
          onMoveUp={() => moveStep(idx, 'up')}
          onMoveDown={() => moveStep(idx, 'down')}
          canMoveUp={idx > 0}
          canMoveDown={idx < steps.length - 1}
          legacyPhaseNames={legacyPhaseNames}
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
