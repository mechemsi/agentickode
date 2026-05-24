// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Server,
  X,
} from "lucide-react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { getProjectWorkspaceReadiness } from "../../api/projects";
import { createSession } from "../../api/sessions";
import type { ProjectConfig, WorkspaceReadinessItem } from "../../types";

interface LaunchAgentModalProps {
  project: ProjectConfig;
  onClose: () => void;
}

type Step = "checking" | "select" | "launching" | "terminal" | "error";

export default function LaunchAgentModal({ project, onClose }: LaunchAgentModalProps) {
  const [step, setStep] = useState<Step>("checking");
  const [workspaces, setWorkspaces] = useState<WorkspaceReadinessItem[]>([]);
  const [selectedServer, setSelectedServer] = useState<WorkspaceReadinessItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const termContainerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);

  const launchOnWorkspace = useCallback(async (ws: WorkspaceReadinessItem) => {
    setSelectedServer(ws);
    setStep("launching");
    setError(null);
    try {
      const session = await createSession({
        workspace_server_id: ws.server_id,
        agent_name: "claude",
        project_id: project.project_id,
        workspace_path: ws.path,
        user_context: "root",
        display_name: `claude @ ${project.project_slug}`,
      });
      setSessionId(session.session_id);
      setStep("terminal");
    } catch (e) {
      setError(`Failed to launch session: ${e instanceof Error ? e.message : "unknown"}`);
      setStep("error");
    }
  }, [project.project_id, project.project_slug]);

  const checkReadiness = useCallback(async () => {
    setStep("checking");
    setError(null);
    try {
      const data = await getProjectWorkspaceReadiness(project.project_id);
      setWorkspaces(data.workspaces);

      if (data.workspaces.length === 0) {
        setError("No workspace servers assigned to this project.");
        setStep("error");
        return;
      }

      const ready = data.workspaces.filter((w) => w.status === "ready");
      if (ready.length === 1) {
        await launchOnWorkspace(ready[0]);
      } else {
        setStep("select");
      }
    } catch (e) {
      setError(`Failed to check workspaces: ${e instanceof Error ? e.message : "unknown error"}`);
      setStep("error");
    }
  }, [project.project_id, launchOnWorkspace]);

  // Terminal setup when session is ready
  useEffect(() => {
    if (step !== "terminal" || !sessionId || !termContainerRef.current) return;

    const el = termContainerRef.current;
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: "ui-monospace, Menlo, Monaco, 'Cascadia Code', monospace",
      theme: {
        background: "#0d1117",
        foreground: "#c9d1d9",
        cursor: "#58a6ff",
        selectionBackground: "#264f78",
      },
    });
    termRef.current = term;

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon());
    term.open(el);
    fitAddon.fit();

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${proto}//${window.location.host}/ws/sessions/${sessionId}/terminal`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    };

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "output") {
        term.write(msg.data);
      }
    };

    ws.onclose = () => {
      term.write("\r\n\x1b[33m[Session ended]\x1b[0m\r\n");
    };

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    const observer = new ResizeObserver(() => {
      fitAddon.fit();
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
      ws.close();
      term.dispose();
    };
  }, [step, sessionId]);

  useEffect(() => {
    checkReadiness();
  }, [checkReadiness]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        className={`bg-gray-900 border border-gray-700 rounded-xl shadow-2xl flex flex-col ${
          step === "terminal"
            ? "w-[90vw] h-[85vh]"
            : "w-full max-w-lg"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-gray-200">
            Launch Claude — {project.project_slug}
          </h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-800 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-hidden">
          {step === "checking" && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
              <p className="text-sm text-gray-400">Checking workspace readiness...</p>
            </div>
          )}

          {step === "select" && (
            <div className="p-5 space-y-3">
              <p className="text-sm text-gray-400 mb-4">
                Select a workspace server to launch Claude on:
              </p>
              {workspaces.map((ws) => (
                <button
                  key={ws.server_id}
                  onClick={() => ws.status === "ready" && launchOnWorkspace(ws)}
                  disabled={ws.status !== "ready"}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-colors ${
                    ws.status === "ready"
                      ? "border-gray-700 hover:border-cyan-600/50 hover:bg-gray-800/50 cursor-pointer"
                      : "border-gray-800 opacity-60 cursor-not-allowed"
                  }`}
                >
                  <Server className={`w-4 h-4 flex-shrink-0 ${
                    ws.status === "ready" ? "text-green-400" : "text-gray-500"
                  }`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-200">{ws.server_name}</p>
                    {ws.path && (
                      <p className="text-xs text-gray-500 truncate">{ws.path}</p>
                    )}
                  </div>
                  {ws.status === "ready" && (
                    <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0" />
                  )}
                  {ws.status === "not_cloned" && (
                    <span className="text-xs text-amber-400">Not cloned</span>
                  )}
                  {ws.status === "unreachable" && (
                    <span className="text-xs text-red-400">Unreachable</span>
                  )}
                </button>
              ))}
            </div>
          )}

          {step === "launching" && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
              <p className="text-sm text-gray-400">
                Launching Claude on {selectedServer?.server_name}...
              </p>
            </div>
          )}

          {step === "terminal" && (
            <div ref={termContainerRef} className="h-full w-full overflow-hidden" />
          )}

          {step === "error" && (
            <div className="flex flex-col items-center justify-center py-12 gap-3 px-5">
              <AlertCircle className="w-6 h-6 text-red-400" />
              <p className="text-sm text-red-300 text-center">{error}</p>
              <button
                onClick={checkReadiness}
                className="mt-2 px-4 py-1.5 rounded bg-gray-800 text-gray-300 text-sm hover:bg-gray-700"
              >
                Retry
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
