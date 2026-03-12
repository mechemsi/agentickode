// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState, useCallback } from "react";
import { ChevronDown, ChevronRight, Eye, History, Key, Plus, Save, Trash2 } from "lucide-react";
import {
  createSecret, deleteInstruction, deleteSecret, getInstructions,
  getInstructionVersions, getSecrets, previewPrompt,
  updateSecret, upsertGlobalInstruction, upsertPhaseInstruction,
} from "../../api";
import type { InstructionVersion, ProjectInstruction, ProjectSecret, PromptPreview } from "../../types";

const PHASES = ["planning", "coding", "reviewing"] as const;
const PLACEHOLDER = `## Rules & Guidelines\n\n## Testing\n- Run tests: \`...\`\n\n## Build & Deploy\n- Build: \`...\`\n\n## Notes\n`;

interface Props { projectId: string }

export default function ProjectInstructionsTab({ projectId }: Props) {
  const [instructions, setInstructions] = useState<ProjectInstruction[]>([]);
  const [secrets, setSecrets] = useState<ProjectSecret[]>([]);
  const [globalContent, setGlobalContent] = useState("");
  const [phaseContent, setPhaseContent] = useState<Record<string, string>>({});
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [newSecret, setNewSecret] = useState({ name: "", value: "", inject_as: "env_var", phase_scope: "" });
  const [showAddSecret, setShowAddSecret] = useState(false);
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [previewPhase, setPreviewPhase] = useState("coding");
  const [versions, setVersions] = useState<InstructionVersion[]>([]);
  const [showVersions, setShowVersions] = useState(false);

  const load = useCallback(async () => {
    const [instrs, secs] = await Promise.all([getInstructions(projectId), getSecrets(projectId)]);
    setInstructions(instrs);
    setSecrets(secs);
    const global = instrs.find(i => i.phase_name === "__global__");
    setGlobalContent(global?.content ?? "");
    const pc: Record<string, string> = {};
    for (const phase of PHASES) {
      const found = instrs.find(i => i.phase_name === phase);
      if (found) pc[phase] = found.content;
    }
    setPhaseContent(pc);
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const saveGlobal = async () => {
    setSaving(true);
    try { await upsertGlobalInstruction(projectId, globalContent); await load(); } finally { setSaving(false); }
  };

  const savePhase = async (phase: string) => {
    setSaving(true);
    try {
      const content = phaseContent[phase];
      if (content?.trim()) {
        await upsertPhaseInstruction(projectId, phase, content);
      } else {
        const existing = instructions.find(i => i.phase_name === phase);
        if (existing) await deleteInstruction(projectId, phase);
      }
      await load();
    } finally { setSaving(false); }
  };

  const handleAddSecret = async () => {
    await createSecret(projectId, {
      name: newSecret.name, value: newSecret.value,
      inject_as: newSecret.inject_as,
      phase_scope: newSecret.phase_scope || null,
    });
    setNewSecret({ name: "", value: "", inject_as: "env_var", phase_scope: "" });
    setShowAddSecret(false);
    await load();
  };

  const handleDeleteSecret = async (id: number) => {
    if (!confirm("Delete this secret?")) return;
    await deleteSecret(projectId, id);
    await load();
  };

  const handleToggleInjectAs = async (secret: ProjectSecret) => {
    const next = secret.inject_as === "env_var" ? "prompt" : "env_var";
    await updateSecret(projectId, secret.id, { inject_as: next });
    await load();
  };

  const loadPreview = async () => {
    setPreview(await previewPrompt(projectId, previewPhase));
  };

  const loadVersions = async () => {
    setVersions(await getInstructionVersions(projectId));
    setShowVersions(true);
  };

  const togglePhase = (phase: string) => {
    setExpandedPhases(prev => {
      const next = new Set(prev);
      if (next.has(phase)) { next.delete(phase); } else { next.add(phase); }
      return next;
    });
  };

  return (
    <div className="space-y-6">
      {/* Global Instructions */}
      <div>
        <h3 className="text-sm font-medium text-gray-300 mb-2">Global Instructions</h3>
        <textarea
          value={globalContent}
          onChange={e => setGlobalContent(e.target.value)}
          placeholder={PLACEHOLDER}
          className="w-full h-40 bg-gray-900/60 border border-gray-700/50 rounded-lg p-3 text-sm text-gray-200 font-mono resize-y focus:outline-none focus:ring-1 focus:ring-blue-500/40"
        />
        <button onClick={saveGlobal} disabled={saving}
          className="mt-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs inline-flex items-center gap-1.5 disabled:opacity-50">
          <Save className="w-3 h-3" /> Save Global
        </button>
      </div>

      {/* Phase-Specific Overrides */}
      <div>
        <h3 className="text-sm font-medium text-gray-300 mb-2">Phase-Specific Overrides</h3>
        <div className="space-y-2">
          {PHASES.map(phase => (
            <div key={phase} className="border border-gray-700/50 rounded-lg overflow-hidden">
              <button onClick={() => togglePhase(phase)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-gray-800/50 transition-colors">
                {expandedPhases.has(phase) ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                <span className="capitalize">{phase}</span>
                {phaseContent[phase] && <span className="text-xs text-blue-400 ml-auto">configured</span>}
              </button>
              {expandedPhases.has(phase) && (
                <div className="px-3 pb-3">
                  <textarea
                    value={phaseContent[phase] ?? ""}
                    onChange={e => setPhaseContent(prev => ({ ...prev, [phase]: e.target.value }))}
                    placeholder={`Override instructions for ${phase} phase...`}
                    className="w-full h-28 bg-gray-900/60 border border-gray-700/50 rounded-lg p-3 text-sm text-gray-200 font-mono resize-y focus:outline-none focus:ring-1 focus:ring-blue-500/40"
                  />
                  <button onClick={() => savePhase(phase)} disabled={saving}
                    className="mt-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs inline-flex items-center gap-1.5 disabled:opacity-50">
                    <Save className="w-3 h-3" /> Save {phase}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Secrets */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-300 inline-flex items-center gap-1.5">
            <Key className="w-3.5 h-3.5" /> Secrets
          </h3>
          <button onClick={() => setShowAddSecret(!showAddSecret)}
            className="text-xs text-blue-400 hover:text-blue-300 inline-flex items-center gap-1">
            <Plus className="w-3 h-3" /> Add Secret
          </button>
        </div>

        {showAddSecret && (
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-3 mb-3 space-y-2">
            <input value={newSecret.name} onChange={e => setNewSecret(p => ({ ...p, name: e.target.value }))}
              placeholder="SECRET_NAME" className="w-full bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1.5 text-sm text-gray-200 font-mono" />
            <input value={newSecret.value} onChange={e => setNewSecret(p => ({ ...p, value: e.target.value }))}
              placeholder="secret value" type="password" className="w-full bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1.5 text-sm text-gray-200" />
            <div className="flex gap-2">
              <select value={newSecret.inject_as} onChange={e => setNewSecret(p => ({ ...p, inject_as: e.target.value }))}
                className="bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1.5 text-sm text-gray-200">
                <option value="env_var">Env Var</option>
                <option value="prompt">Prompt</option>
              </select>
              <input value={newSecret.phase_scope} onChange={e => setNewSecret(p => ({ ...p, phase_scope: e.target.value }))}
                placeholder="phase scope (e.g. coding,reviewing)" className="flex-1 bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1.5 text-sm text-gray-200" />
            </div>
            <button onClick={handleAddSecret} disabled={!newSecret.name || !newSecret.value}
              className="px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white rounded text-xs disabled:opacity-50">Add</button>
          </div>
        )}

        {secrets.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs border-b border-gray-800">
                <th className="text-left py-1.5">Name</th>
                <th className="text-left py-1.5">Value</th>
                <th className="text-left py-1.5">Type</th>
                <th className="text-left py-1.5">Scope</th>
                <th className="py-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {secrets.map(s => (
                <tr key={s.id} className="border-b border-gray-800/50 text-gray-300">
                  <td className="py-1.5 font-mono text-xs">{s.name}</td>
                  <td className="py-1.5 text-gray-500">***</td>
                  <td className="py-1.5">
                    <button onClick={() => handleToggleInjectAs(s)}
                      className="text-xs px-1.5 py-0.5 rounded bg-gray-800 hover:bg-gray-700 transition-colors">
                      {s.inject_as}
                    </button>
                  </td>
                  <td className="py-1.5 text-xs text-gray-500">{s.phase_scope || "all"}</td>
                  <td className="py-1.5 text-right">
                    <button onClick={() => handleDeleteSecret(s.id)} className="text-red-400 hover:text-red-300">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-xs text-gray-500">No secrets configured.</p>
        )}
      </div>

      {/* Prompt Preview */}
      <div>
        <h3 className="text-sm font-medium text-gray-300 mb-2 inline-flex items-center gap-1.5">
          <Eye className="w-3.5 h-3.5" /> Prompt Preview
        </h3>
        <div className="flex gap-2 mb-2">
          <select value={previewPhase} onChange={e => setPreviewPhase(e.target.value)}
            className="bg-gray-900/60 border border-gray-700/50 rounded px-2 py-1.5 text-sm text-gray-200">
            {PHASES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <button onClick={loadPreview}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">Preview</button>
        </div>
        {preview && (
          <div className="bg-gray-900/60 border border-gray-700/50 rounded-lg p-3">
            <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono max-h-60 overflow-y-auto">{preview.system_prompt_section || "(empty)"}</pre>
            {preview.secrets_injected.length > 0 && (
              <p className="text-xs text-yellow-400 mt-2">Secrets injected: {preview.secrets_injected.join(", ")}</p>
            )}
          </div>
        )}
      </div>

      {/* Version History */}
      <div>
        <button onClick={loadVersions}
          className="text-sm text-gray-400 hover:text-gray-300 inline-flex items-center gap-1.5">
          <History className="w-3.5 h-3.5" /> {showVersions ? "Hide" : "Show"} Version History
        </button>
        {showVersions && versions.length > 0 && (
          <div className="mt-2 space-y-2 max-h-60 overflow-y-auto">
            {versions.map(v => (
              <div key={v.id} className="bg-gray-900/60 border border-gray-700/50 rounded-lg p-2">
                <p className="text-xs text-gray-500">{new Date(v.changed_at).toLocaleString()}</p>
                <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono mt-1 max-h-20 overflow-y-auto">{v.content.slice(0, 300)}{v.content.length > 300 ? "..." : ""}</pre>
              </div>
            ))}
          </div>
        )}
        {showVersions && versions.length === 0 && (
          <p className="text-xs text-gray-500 mt-2">No version history yet.</p>
        )}
      </div>
    </div>
  );
}