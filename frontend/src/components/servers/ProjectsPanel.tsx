// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { createPortal } from "react-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { getProjectsByServer } from "../../api";
import type { ProjectConfig, WorkspaceServer } from "../../types";
import { generateVSCodeURI, generateJetBrainsGatewayURI, JETBRAINS_IDES } from "../../utils/vscode";
import type { JetBrainsIDE } from "../../utils/vscode";

function IDEPicker({
  server,
  remotePath,
  anchorRef,
  onClose,
}: {
  server: WorkspaceServer;
  remotePath: string;
  anchorRef: React.RefObject<React.ElementRef<"button"> | null>;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (anchorRef.current) {
      const rect = anchorRef.current.getBoundingClientRect();
      setPos({ top: rect.bottom + 4, left: rect.right - 160 });
    }
  }, [anchorRef]);

  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handler = (e: any) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [onClose]);

  const openIDE = (ide: JetBrainsIDE) => {
    window.localStorage.setItem("autodev-jetbrains-ide", ide);
    window.location.href = generateJetBrainsGatewayURI(server, remotePath, ide);
    onClose();
  };

  return createPortal(
    <div
      ref={ref}
      style={{ position: "fixed", top: pos.top, left: pos.left }}
      className="z-[9999] bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[160px]"
    >
      <span className="text-xs text-gray-500 px-3 py-1 block">Open with...</span>
      {JETBRAINS_IDES.map((ide) => (
        <button
          key={ide.id}
          onClick={() => openIDE(ide.id)}
          className="w-full text-left text-xs text-gray-300 hover:text-white hover:bg-gray-700/60 px-3 py-1.5 transition-colors"
        >
          {ide.label}
        </button>
      ))}
    </div>,
    window.document.body,
  );
}

function ProjectRow({ project, server }: { project: ProjectConfig; server?: WorkspaceServer }) {
  const needsSshConfig = server && server.port !== 22;
  const [showPicker, setShowPicker] = useState(false);
  const btnRef = useRef<React.ElementRef<"button">>(null);
  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-800/30 transition-colors">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-white">{project.project_slug}</span>
          <span className="text-xs text-gray-500 font-mono">
            {project.repo_owner}/{project.repo_name}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800/50 text-gray-400">
            {project.git_provider}
          </span>
          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800/50 text-gray-400">
            {project.task_source}
          </span>
          <span className="text-xs text-gray-500">{project.default_branch}</span>
        </div>
      </div>
      {project.workspace_path && server && (
        <div className="flex items-center gap-2 shrink-0 ml-4">
          {needsSshConfig && (
            <span className="text-xs text-yellow-500" title={`Port ${server.port} requires SSH config`}>
              SSH config needed
            </span>
          )}
          <a
            href={generateVSCodeURI(server, project.workspace_path)}
            className="text-xs text-gray-400 hover:text-blue-400 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
            title="Open in VS Code (requires Remote-SSH extension)"
          >
            <ExternalLink className="w-3 h-3" /> VS Code
          </a>
          <button
            ref={btnRef}
            onClick={() => setShowPicker((v) => !v)}
            className="text-xs text-gray-400 hover:text-purple-400 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
            title="Open in JetBrains Gateway"
          >
            <ExternalLink className="w-3 h-3" /> JetBrains
          </button>
          {showPicker && (
            <IDEPicker
              server={server}
              remotePath={project.workspace_path}
              anchorRef={btnRef}
              onClose={() => setShowPicker(false)}
            />
          )}
        </div>
      )}
    </div>
  );
}

export default function ProjectsPanel({ serverId, server }: { serverId: number; server?: WorkspaceServer }) {
  const [projects, setProjects] = useState<ProjectConfig[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getProjectsByServer(serverId);
      setProjects(result);
    } catch {
      setError("Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, [serverId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !projects) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-xs py-2">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading projects...
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-300">Projects</span>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-gray-500 hover:text-gray-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>
      {error && (
        <p className="text-red-400 text-xs px-3 py-1">{error}</p>
      )}
      {projects && projects.length === 0 && (
        <p className="text-gray-500 text-xs px-3 py-1">No projects linked to this server.</p>
      )}
      {projects?.map((p) => (
        <ProjectRow key={p.project_id} project={p} server={server} />
      ))}
    </div>
  );
}