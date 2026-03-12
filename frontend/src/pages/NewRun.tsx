// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, GitBranch, Plus } from "lucide-react";
import {
  createRun,
  getProjectIssues,
  getProjects,
  getWorkflowTemplates,
  getWorkspaceServers,
} from "../api";
import { useToast } from "../components/shared/Toast";
import { AGENT_NAMES } from "../types";
import type { GitIssue, ProjectConfig, WorkflowTemplate, WorkspaceServer } from "../types";

const PHASES_WITH_AGENTS = [
  "workspace_setup",
  "init",
  "planning",
  "coding",
  "reviewing",
  "finalization",
];

export default function NewRun() {
  const navigate = useNavigate();
  const toast = useToast();

  const [projects, setProjects] = useState<ProjectConfig[]>([]);
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [servers, setServers] = useState<WorkspaceServer[]>([]);

  const [projectId, setProjectId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [workflowTemplateId, setWorkflowTemplateId] = useState<number | "">("");
  const [labels, setLabels] = useState("");
  const [runType] = useState("ai_task");

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [agentOverride, setAgentOverride] = useState("");
  const [workspaceServerId, setWorkspaceServerId] = useState<number | "">("");
  const [phaseOverrides, setPhaseOverrides] = useState<Record<string, string>>({});
  const [subtaskMode, setSubtaskMode] = useState<"separate" | "batch">("batch");

  const [issues, setIssues] = useState<GitIssue[]>([]);
  const [issuesLoading, setIssuesLoading] = useState(false);
  const [issuesError, setIssuesError] = useState("");
  const [selectedIssue, setSelectedIssue] = useState<GitIssue | null>(null);

  const [skipSchedule, setSkipSchedule] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    Promise.all([getProjects(), getWorkflowTemplates(), getWorkspaceServers()]).then(
      ([p, t, s]) => {
        setProjects(p);
        setTemplates(t);
        setServers(s);
      },
    );
  }, []);

  useEffect(() => {
    setIssues([]);
    setSelectedIssue(null);
    setIssuesError("");
    if (!projectId) return;
    const project = projects.find((p) => p.project_id === projectId);
    if (!project || project.task_source === "plain") return;

    setIssuesLoading(true);
    getProjectIssues(projectId)
      .then(setIssues)
      .catch((err) => {
        setIssues([]);
        setIssuesError(err instanceof Error ? err.message : "Failed to load issues");
      })
      .finally(() => setIssuesLoading(false));
  }, [projectId, projects]);

  const handleIssueSelect = (issueNumber: string) => {
    if (!issueNumber) {
      setSelectedIssue(null);
      return;
    }
    const issue = issues.find((i) => i.number === parseInt(issueNumber));
    if (issue) {
      setSelectedIssue(issue);
      setTitle(issue.title);
      setDescription(issue.body);
    }
  };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!projectId) errs.project_id = "Project is required";
    if (!title.trim()) errs.title = "Title is required";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    try {
      const labelList = labels
        .split(",")
        .map((l) => l.trim())
        .filter(Boolean);

      const phaseOverridesPayload: Record<string, Record<string, unknown>> = {};
      for (const [phase, agent] of Object.entries(phaseOverrides)) {
        if (agent) {
          phaseOverridesPayload[phase] = { agent_override: agent };
        }
      }
      if (subtaskMode === "batch") {
        phaseOverridesPayload["coding"] = {
          ...phaseOverridesPayload["coding"],
          params: { subtask_mode: "batch" },
        };
      }

      const result = await createRun({
        project_id: projectId,
        title: title.trim(),
        description: description.trim(),
        workflow_template_id: workflowTemplateId !== "" ? workflowTemplateId : null,
        labels: labelList,
        run_type: runType,
        agent_override: agentOverride || null,
        workspace_server_id: workspaceServerId !== "" ? workspaceServerId : null,
        phase_overrides:
          Object.keys(phaseOverridesPayload).length > 0 ? phaseOverridesPayload : null,
        issue_number: selectedIssue?.number ?? null,
        issue_url: selectedIssue?.url ?? null,
        skip_schedule: skipSchedule || undefined,
      });

      toast.success(`Run #${result.id} created`);
      navigate(`/runs/${result.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create run");
    } finally {
      setSubmitting(false);
    }
  };

  const setPhaseAgent = (phase: string, agent: string) => {
    setPhaseOverrides((prev) => ({ ...prev, [phase]: agent }));
  };

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-blue-400" />
          New Run
        </h1>
      </div>

      <form onSubmit={handleSubmit} className="max-w-2xl">
        {/* Core fields */}
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 backdrop-blur-sm space-y-4 mb-4">
          {/* Project */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Project <span className="text-red-400">*</span>
            </label>
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
            >
              <option value="">-- Select project --</option>
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.project_slug} ({p.repo_owner}/{p.repo_name})
                </option>
              ))}
            </select>
            {errors.project_id && (
              <p className="text-red-400 text-xs mt-1">{errors.project_id}</p>
            )}
          </div>

          {/* Issue picker */}
          {projectId && issuesLoading && (
            <p className="text-xs text-gray-500">Loading issues...</p>
          )}
          {projectId && !issuesLoading && issuesError && (
            <p className="text-amber-400 text-xs mt-1">
              Could not load issues: {issuesError}
            </p>
          )}
          {projectId && !issuesLoading && !issuesError && issues.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                From Issue
                <span className="text-gray-500 font-normal ml-1 text-xs">optional</span>
              </label>
              <select
                value={selectedIssue?.number ?? ""}
                onChange={(e) => handleIssueSelect(e.target.value)}
                className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
              >
                <option value="">-- Type manually --</option>
                {issues.map((issue) => (
                  <option key={issue.number} value={issue.number}>
                    #{issue.number}: {issue.title}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Title <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Fix the login form validation"
              className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
            />
            {errors.title && (
              <p className="text-red-400 text-xs mt-1">{errors.title}</p>
            )}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="Describe what needs to be done..."
              className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40 resize-y"
            />
          </div>

          {/* Workflow Template */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Workflow Template
            </label>
            <select
              value={workflowTemplateId}
              onChange={(e) =>
                setWorkflowTemplateId(e.target.value !== "" ? parseInt(e.target.value) : "")
              }
              className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
            >
              <option value="">None (use project default)</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                  {t.is_default ? " (default)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Labels */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Labels
              <span className="text-gray-500 font-normal ml-1 text-xs">comma-separated</span>
            </label>
            <input
              type="text"
              value={labels}
              onChange={(e) => setLabels(e.target.value)}
              placeholder="bug, frontend, urgent"
              className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
            />
          </div>

          {/* Skip Schedule */}
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={skipSchedule}
              onChange={(e) => setSkipSchedule(e.target.checked)}
              className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500/40 focus:ring-offset-0"
            />
            <div>
              <span className="text-sm font-medium text-gray-300">Skip schedule</span>
              <p className="text-xs text-gray-500">
                Bypass queue schedule and dispatch this run right away
              </p>
            </div>
          </label>
        </div>

        {/* Advanced section */}
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl backdrop-blur-sm mb-6">
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="w-full flex items-center justify-between px-5 py-3.5 text-sm font-medium text-gray-300 hover:text-white transition-colors"
          >
            <span className="flex items-center gap-2">
              {showAdvanced ? (
                <ChevronDown className="w-4 h-4 text-gray-400" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-400" />
              )}
              Advanced Options
            </span>
          </button>

          {showAdvanced && (
            <div className="px-5 pb-5 space-y-4 border-t border-gray-800/60 pt-4">
              {/* Agent Override */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">
                  Agent Override
                  <span className="text-gray-500 font-normal ml-1 text-xs">
                    applies to all phases
                  </span>
                </label>
                <select
                  value={agentOverride}
                  onChange={(e) => setAgentOverride(e.target.value)}
                  className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
                >
                  <option value="">Use project default</option>
                  {AGENT_NAMES.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </div>

              {/* Workspace Server */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">
                  Workspace Server
                </label>
                <select
                  value={workspaceServerId}
                  onChange={(e) =>
                    setWorkspaceServerId(e.target.value !== "" ? parseInt(e.target.value) : "")
                  }
                  className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
                >
                  <option value="">Use project default</option>
                  {servers.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.hostname})
                    </option>
                  ))}
                </select>
              </div>

              {/* Subtask mode */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">
                  Subtask Execution Mode
                </label>
                <select
                  value={subtaskMode}
                  onChange={(e) => setSubtaskMode(e.target.value as "separate" | "batch")}
                  className="w-full bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
                >
                  <option value="batch">Batch — all subtasks in one prompt (saves tokens)</option>
                  <option value="separate">Separate — one agent call per subtask</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Batch mode sends all subtasks in a single prompt, reducing token usage but giving less granular control.
                </p>
              </div>

              {/* Per-phase overrides */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Per-Phase Agent Overrides
                </label>
                <div className="space-y-2">
                  {PHASES_WITH_AGENTS.map((phase) => (
                    <div key={phase} className="flex items-center gap-3">
                      <span className="text-sm text-gray-400 w-36 shrink-0 font-mono">
                        {phase}
                      </span>
                      <select
                        value={phaseOverrides[phase] ?? ""}
                        onChange={(e) => setPhaseAgent(phase, e.target.value)}
                        className="flex-1 bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
                      >
                        <option value="">Inherit</option>
                        {AGENT_NAMES.map((a) => (
                          <option key={a} value={a}>
                            {a}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Submit */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium inline-flex items-center gap-2 shadow-sm shadow-blue-900/30 focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-colors"
          >
            <Plus className="w-4 h-4" />
            {submitting ? "Creating..." : "Create Run"}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-5 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm font-medium focus:outline-none focus:ring-2 focus:ring-gray-600/40 transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </>
  );
}