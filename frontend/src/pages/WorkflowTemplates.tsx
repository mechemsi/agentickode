// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  GitBranch,
  Plus,
  Shield,
  Trash2,
} from 'lucide-react';
import {
  createWorkflowTemplate,
  deleteWorkflowTemplate,
  getPhases,
  getStepKinds,
  getWorkflowTemplates,
  updateWorkflowTemplate,
} from '../api';
import type {
  PhaseConfig,
  PhaseInfo,
  StepKindDescriptor,
  WorkflowTemplate,
} from '../types';
import { useConfirm } from '../components/shared/ConfirmDialog';
import { useToast } from '../components/shared/Toast';
import { StepListEditor } from '../components/workflows';

export default function WorkflowTemplates() {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [availablePhases, setAvailablePhases] = useState<PhaseInfo[]>([]);
  const [stepKinds, setStepKinds] = useState<StepKindDescriptor[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();
  const toast = useToast();

  // New template form
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');

  const legacyPhaseNames = useMemo(() => {
    const descriptor = stepKinds.find((s) => s.kind === 'legacy_phase');
    if (descriptor?.values && descriptor.values.length > 0) {
      return descriptor.values;
    }
    return availablePhases.map((p) => p.name);
  }, [stepKinds, availablePhases]);

  const load = async () => {
    try {
      const [t, ph, sk] = await Promise.all([
        getWorkflowTemplates(),
        getPhases(),
        getStepKinds().catch(() => [] as StepKindDescriptor[]),
      ]);
      setTemplates(t);
      setAvailablePhases(ph);
      setStepKinds(sk);
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
        kind: 'legacy_phase',
        enabled: true,
        role: null,
        uses_agent: p.default_role ? true : null,
        trigger_mode: p.name === 'approval' ? 'wait_for_approval' : 'auto',
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
      setNewName('');
      setNewDesc('');
      setShowForm(false);
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleDelete = async (t: WorkflowTemplate) => {
    const ok = await confirm({
      title: 'Delete Workflow',
      message: `Delete workflow "${t.name}"? This cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
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

  const persistPhases = async (t: WorkflowTemplate, phases: PhaseConfig[]) => {
    // Optimistically update local state so the editor stays responsive.
    setTemplates((prev) =>
      prev.map((tmpl) => (tmpl.id === t.id ? { ...tmpl, phases } : tmpl)),
    );
    try {
      await updateWorkflowTemplate(t.id, { phases });
    } catch (e) {
      toast.error(String(e));
      // Reload to revert on failure.
      await load();
    }
  };

  const handleLabelRuleChange = async (
    t: WorkflowTemplate,
    ruleIdx: number,
    field: 'match_all' | 'match_any',
    value: string,
  ) => {
    const rules = [...(t.label_rules || [])];
    rules[ruleIdx] = {
      ...rules[ruleIdx],
      [field]: value
        .split(',')
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
                setNewName('');
                setNewDesc('');
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
                  {t.phases.filter((p) => p.enabled).length}/{t.phases.length}{' '}
                  steps
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
                {t.description && (
                  <p className="text-xs text-gray-500">{t.description}</p>
                )}

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
                            defaultValue={(rule.match_all || []).join(', ')}
                            onBlur={(e) =>
                              handleLabelRuleChange(
                                t,
                                ri,
                                'match_all',
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
                            defaultValue={(rule.match_any || []).join(', ')}
                            onBlur={(e) =>
                              handleLabelRuleChange(
                                t,
                                ri,
                                'match_any',
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

                {/* Steps composer */}
                <div>
                  <label className="block text-xs text-gray-400 font-medium mb-2">
                    Steps
                  </label>
                  <StepListEditor
                    steps={t.phases}
                    onChange={(next) => persistPhases(t, next)}
                    legacyPhaseNames={legacyPhaseNames}
                  />
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
