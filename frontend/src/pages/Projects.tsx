// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { FileText, FolderKanban, Pencil, Plus, Trash2 } from "lucide-react";
import { createProject, deleteProject, getProjects, getWorkspaceServers, updateProject } from "../api";
import ProjectForm from "../components/shared/ProjectForm";
import ProjectInstructionsTab from "../components/settings/ProjectInstructionsTab";
import type { ProjectConfig, WorkspaceServer } from "../types";

export default function Projects() {
  const [projects, setProjects] = useState<ProjectConfig[]>([]);
  const [servers, setServers] = useState<WorkspaceServer[]>([]);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [instructionsFor, setInstructionsFor] = useState<string | null>(null);

  const load = async () => setProjects(await getProjects());
  useEffect(() => { load(); getWorkspaceServers().then(setServers); }, []);

  const handleCreate = async (data: Record<string, unknown>) => {
    await createProject(data as Partial<ProjectConfig>);
    setEditing(null);
    load();
  };

  const handleUpdate = async (id: string, data: Record<string, unknown>) => {
    await updateProject(id, data as Partial<ProjectConfig>);
    setEditing(null);
    load();
  };

  const handleDelete = async (id: string) => {
    if (!confirm(`Delete project ${id}?`)) return;
    await deleteProject(id);
    load();
  };

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <FolderKanban className="w-5 h-5 text-blue-400" />
          Projects
        </h1>
        <button
          onClick={() => setEditing("new")}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm inline-flex items-center gap-1.5 shadow-sm shadow-blue-900/30 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        >
          <Plus className="w-4 h-4" />
          Add Project
        </button>
      </div>

      {editing === "new" && (
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-5 mb-4 animate-fade-in">
          <ProjectForm onSubmit={handleCreate} onCancel={() => setEditing(null)} servers={servers} />
        </div>
      )}

      <div className="space-y-3">
        {projects.map((p) => (
          <div key={p.project_id} className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 hover:border-gray-700/60 hover:bg-gray-900/60 transition-all group backdrop-blur-sm">
            {editing === p.project_id ? (
              <ProjectForm
                initial={p}
                onSubmit={(data) => handleUpdate(p.project_id, data)}
                onCancel={() => setEditing(null)}
                servers={servers}
              />
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium text-white">{p.project_slug}</span>
                  <span className="text-gray-500 ml-3 text-sm">
                    {p.repo_owner}/{p.repo_name} · {p.task_source}/{p.git_provider}
                  </span>
                </div>
                <div className="flex gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => setInstructionsFor(instructionsFor === p.project_id ? null : p.project_id)}
                    className="text-xs text-purple-400 hover:text-purple-300 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-purple-900/20 transition-colors"
                  >
                    <FileText className="w-3 h-3" />
                    Instructions
                  </button>
                  <button
                    onClick={() => setEditing(p.project_id)}
                    className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                  >
                    <Pencil className="w-3 h-3" />
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(p.project_id)}
                    className="text-xs text-red-400 hover:text-red-300 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-red-900/20 transition-colors"
                  >
                    <Trash2 className="w-3 h-3" />
                    Delete
                  </button>
                </div>
              </div>
            )}
            {instructionsFor === p.project_id && (
              <div className="mt-3 pt-3 border-t border-gray-800/50">
                <ProjectInstructionsTab projectId={p.project_id} />
              </div>
            )}
          </div>
        ))}
        {projects.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500 bg-gray-900/40 border border-gray-800/60 rounded-xl backdrop-blur-sm">
            <FolderKanban className="w-8 h-8 mb-2 text-gray-600" />
            <p className="text-sm">No projects configured yet.</p>
          </div>
        )}
      </div>
    </>
  );
}