// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useState } from "react";
import {
  Check,
  Clock,
  Loader2,
  Pause,
  Pencil,
  Play,
  Plus,
  Trash2,
  Zap,
} from "lucide-react";

interface PlatformCron {
  id: number;
  name: string;
  description: string | null;
  schedule: string;
  prompt: string;
  session_id: string | null;
  agent_name: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_result: string | null;
  run_count: number;
  execution_log: Array<{ at: string; result: string }>;
  created_at: string;
}

const RESULT_COLORS: Record<string, string> = {
  success: "text-green-400",
  send_error: "text-red-400",
  session_not_found: "text-yellow-400",
  session_dead: "text-yellow-400",
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function PlatformCrons() {
  const [crons, setCrons] = useState<PlatformCron[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [triggering, setTriggering] = useState<number | null>(null);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formSchedule, setFormSchedule] = useState("*/30 * * * *");
  const [formPrompt, setFormPrompt] = useState("");
  const [formAgent, setFormAgent] = useState("claude");
  const [formSessionId, setFormSessionId] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchCrons = useCallback(async () => {
    try {
      const res = await fetch("/api/platform-crons");
      if (res.ok) setCrons(await res.json());
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchCrons(); }, [fetchCrons]);

  // Auto-refresh every 30s
  useEffect(() => {
    const iv = setInterval(fetchCrons, 30000);
    return () => clearInterval(iv);
  }, [fetchCrons]);

  const resetForm = () => {
    setFormName("");
    setFormDesc("");
    setFormSchedule("*/30 * * * *");
    setFormPrompt("");
    setFormAgent("claude");
    setFormSessionId("");
    setEditingId(null);
    setShowForm(false);
  };

  const editCron = (c: PlatformCron) => {
    setFormName(c.name);
    setFormDesc(c.description || "");
    setFormSchedule(c.schedule);
    setFormPrompt(c.prompt);
    setFormAgent(c.agent_name);
    setFormSessionId(c.session_id || "");
    setEditingId(c.id);
    setShowForm(true);
  };

  const saveCron = async () => {
    setSaving(true);
    const body = {
      name: formName,
      description: formDesc || null,
      schedule: formSchedule,
      prompt: formPrompt,
      agent_name: formAgent,
      session_id: formSessionId || null,
    };
    try {
      const url = editingId ? `/api/platform-crons/${editingId}` : "/api/platform-crons";
      const method = editingId ? "PUT" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        resetForm();
        fetchCrons();
      }
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const deleteCron = async (id: number) => {
    await fetch(`/api/platform-crons/${id}`, { method: "DELETE" });
    fetchCrons();
  };

  const toggleCron = async (c: PlatformCron) => {
    await fetch(`/api/platform-crons/${c.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !c.enabled }),
    });
    fetchCrons();
  };

  const triggerCron = async (id: number) => {
    setTriggering(id);
    await fetch(`/api/platform-crons/${id}/trigger`, { method: "POST" });
    setTimeout(() => { fetchCrons(); setTriggering(null); }, 2000);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 py-4">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading crons...
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Clock className="w-5 h-5 text-cyan-400" />
          Platform Crons
        </h2>
        <button
          onClick={() => { resetForm(); setShowForm(true); }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" /> New Cron
        </button>
      </div>

      <p className="text-xs text-gray-500 mb-4">
        Scheduled prompts sent to local agent sessions. Crons auto-resume sessions if closed.
      </p>

      {/* Create/Edit Form */}
      {showForm && (
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 mb-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Name</label>
              <input
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="health-check"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Schedule (cron)</label>
              <input
                value={formSchedule}
                onChange={(e) => setFormSchedule(e.target.value)}
                placeholder="*/30 * * * *"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 font-mono"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Prompt</label>
            <textarea
              value={formPrompt}
              onChange={(e) => setFormPrompt(e.target.value)}
              placeholder="Check if all services are healthy and report any issues"
              rows={3}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200"
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Agent</label>
              <select
                value={formAgent}
                onChange={(e) => setFormAgent(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200"
              >
                <option value="claude">claude</option>
                <option value="codex">codex</option>
                <option value="gemini">gemini</option>
                <option value="aider">aider</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Session ID (optional)</label>
              <input
                value={formSessionId}
                onChange={(e) => setFormSessionId(e.target.value)}
                placeholder="auto"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 font-mono"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Description</label>
              <input
                value={formDesc}
                onChange={(e) => setFormDesc(e.target.value)}
                placeholder="Optional"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              onClick={resetForm}
              className="px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200"
            >
              Cancel
            </button>
            <button
              onClick={saveCron}
              disabled={saving || !formName || !formSchedule || !formPrompt}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-lg"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
              {editingId ? "Update" : "Create"}
            </button>
          </div>
        </div>
      )}

      {/* Cron list */}
      {crons.length === 0 && !showForm && (
        <div className="text-sm text-gray-500 text-center py-8">
          No platform crons yet. Create one to schedule autonomous agent prompts.
        </div>
      )}

      <div className="space-y-2">
        {crons.map((c) => (
          <div key={c.id} className="bg-gray-800/50 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-4 py-3">
              {/* Status dot */}
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${c.enabled ? "bg-green-400" : "bg-gray-600"}`} />

              {/* Name + schedule */}
              <div
                className="flex-1 min-w-0 cursor-pointer"
                onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-200">{c.name}</span>
                  <code className="text-xs text-gray-500 bg-gray-900 px-1.5 py-0.5 rounded">{c.schedule}</code>
                  <span className="text-xs text-gray-600">{c.agent_name}</span>
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-xs text-gray-500">
                    Last: {timeAgo(c.last_run_at)}
                  </span>
                  {c.last_result && (
                    <span className={`text-xs ${RESULT_COLORS[c.last_result] || "text-gray-500"}`}>
                      {c.last_result}
                    </span>
                  )}
                  <span className="text-xs text-gray-600">
                    {c.run_count} runs
                  </span>
                  {c.next_run_at && c.enabled && (
                    <span className="text-xs text-gray-500">
                      Next: {timeAgo(c.next_run_at).replace("ago", "").trim() === "just now" ? "now" : new Date(c.next_run_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  )}
                </div>
              </div>

              {/* Actions */}
              <button
                onClick={() => triggerCron(c.id)}
                disabled={triggering === c.id}
                className="p-1.5 rounded hover:bg-cyan-900/30 text-gray-500 hover:text-cyan-400 disabled:opacity-50"
                title="Trigger now"
              >
                {triggering === c.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              </button>
              <button
                onClick={() => toggleCron(c)}
                className={`p-1.5 rounded ${c.enabled ? "hover:bg-yellow-900/30 text-gray-500 hover:text-yellow-400" : "hover:bg-green-900/30 text-gray-500 hover:text-green-400"}`}
                title={c.enabled ? "Pause" : "Enable"}
              >
                {c.enabled ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              </button>
              <button
                onClick={() => editCron(c)}
                className="p-1.5 rounded hover:bg-gray-700 text-gray-500 hover:text-gray-300"
                title="Edit"
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => deleteCron(c.id)}
                className="p-1.5 rounded hover:bg-red-900/30 text-gray-500 hover:text-red-400"
                title="Delete"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Expanded detail */}
            {expandedId === c.id && (
              <div className="border-t border-gray-700 px-4 py-3 space-y-2">
                <div>
                  <span className="text-xs text-gray-500">Prompt:</span>
                  <p className="text-sm text-gray-300 mt-0.5">{c.prompt}</p>
                </div>
                {c.session_id && (
                  <div className="text-xs text-gray-500">
                    Session: <code className="text-gray-400">{c.session_id}</code>
                  </div>
                )}
                {c.description && (
                  <div className="text-xs text-gray-500">{c.description}</div>
                )}
                {c.execution_log.length > 0 && (
                  <div>
                    <span className="text-xs text-gray-500">Recent executions:</span>
                    <div className="mt-1 space-y-0.5 max-h-32 overflow-y-auto">
                      {[...c.execution_log].reverse().slice(0, 10).map((entry, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <span className="text-gray-600">{new Date(entry.at).toLocaleString()}</span>
                          <span className={RESULT_COLORS[entry.result] || "text-gray-500"}>{entry.result}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
