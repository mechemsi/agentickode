// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

/* global ResizeObserver */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X, Terminal as TerminalIcon, Play, Pause, CheckCircle } from "lucide-react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { runTerminalAction } from "../../api";

interface Props {
  runId: number;
  workspacePath: string;
  onClose: () => void;
  onAction: () => void;
}

export default function RunTerminalDrawer({ runId, workspacePath, onClose, onAction }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const [showActions, setShowActions] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || showActions) return;

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
    const ws = new WebSocket(
      `${proto}//${window.location.host}/ws/runs/${runId}/terminal`,
    );

    ws.onopen = () => {
      ws.send(
        JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }),
      );
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
        ws.send(
          JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }),
        );
      }
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
      ws.close();
      term.dispose();
    };
  }, [runId, showActions]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showActions) {
          setShowActions(false);
        } else {
          handleCloseRequest();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [showActions]);

  const handleCloseRequest = () => {
    setShowActions(true);
  };

  const handleAction = async (action: "continue" | "pause" | "complete") => {
    setActionLoading(true);
    try {
      await runTerminalAction(runId, action);
      onAction();
      onClose();
    } catch {
      setActionLoading(false);
    }
  };

  return createPortal(
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/50 z-[100]" onClick={handleCloseRequest} />

      {/* Drawer from right */}
      <div className="fixed top-0 right-0 bottom-0 w-[60vw] min-w-[480px] max-w-[1200px] bg-gray-900 border-l border-gray-700/50 z-[101] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-700/50 flex-shrink-0">
          <TerminalIcon className="w-4 h-4 text-green-400" />
          <span className="text-sm font-medium text-gray-200 flex-1 truncate">
            Terminal &mdash; {workspacePath}
          </span>
          <button
            onClick={handleCloseRequest}
            className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        {showActions ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="bg-gray-800/80 border border-gray-700/50 rounded-xl p-6 max-w-md w-full mx-4 space-y-4">
              <h3 className="text-lg font-semibold text-gray-100 text-center">
                What would you like to do?
              </h3>
              <p className="text-sm text-gray-400 text-center">
                Choose how to proceed after your terminal session.
              </p>
              <div className="space-y-2">
                <button
                  onClick={() => handleAction("continue")}
                  disabled={actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 bg-green-700/30 hover:bg-green-700/50 border border-green-600/40 rounded-lg text-sm text-green-200 transition-colors disabled:opacity-50"
                >
                  <Play className="w-4 h-4" />
                  <div className="text-left">
                    <div className="font-medium">Continue Pipeline</div>
                    <div className="text-xs text-green-300/70">Resume automated execution from next phase</div>
                  </div>
                </button>
                <button
                  onClick={() => handleAction("pause")}
                  disabled={actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 bg-gray-700/30 hover:bg-gray-700/50 border border-gray-600/40 rounded-lg text-sm text-gray-200 transition-colors disabled:opacity-50"
                >
                  <Pause className="w-4 h-4" />
                  <div className="text-left">
                    <div className="font-medium">Stay Paused</div>
                    <div className="text-xs text-gray-400">Keep the run in its current state</div>
                  </div>
                </button>
                <button
                  onClick={() => handleAction("complete")}
                  disabled={actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 bg-blue-700/30 hover:bg-blue-700/50 border border-blue-600/40 rounded-lg text-sm text-blue-200 transition-colors disabled:opacity-50"
                >
                  <CheckCircle className="w-4 h-4" />
                  <div className="text-left">
                    <div className="font-medium">Mark Completed</div>
                    <div className="text-xs text-blue-300/70">Mark this run as finished</div>
                  </div>
                </button>
              </div>
              <button
                onClick={() => setShowActions(false)}
                className="w-full text-center text-xs text-gray-500 hover:text-gray-300 py-1"
              >
                Back to terminal
              </button>
            </div>
          </div>
        ) : (
          <div
            ref={containerRef}
            className="flex-1 overflow-hidden"
          />
        )}
      </div>
    </>,
    document.body,
  );
}