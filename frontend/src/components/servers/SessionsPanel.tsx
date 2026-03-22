// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useState } from "react";
import {
  Loader2,
  MessageSquare,
  Monitor,
  Plus,
  RefreshCw,
  SquareTerminal,
  X,
} from "lucide-react";
import {
  createSession,
  closeSession,
  listServerSessions,
} from "../../api/sessions";
import type { CliSession, CliSessionCreate } from "../../types/sessions";
import { useConfirm } from "../shared/ConfirmDialog";
import { useToast } from "../shared/Toast";
import TerminalPanel from "../runs/TerminalPanel";
import ChatPanel from "./ChatPanel";

interface SessionsPanelProps {
  serverId: number;
  workerUser: string | null;
}

function statusDotColor(status: CliSession["status"]): string {
  switch (status) {
    case "active":
      return "bg-green-400";
    case "idle":
    case "detached":
      return "bg-yellow-400";
    case "error":
      return "bg-red-400";
    case "starting":
      return "bg-blue-400 animate-pulse";
    case "closed":
      return "bg-gray-500";
    default:
      return "bg-gray-500";
  }
}

function relativeTime(dateStr: string): string {
  const ago = Date.now() - new Date(dateStr).getTime();
  if (ago < 60_000) return "just now";
  if (ago < 3_600_000) return `${Math.floor(ago / 60_000)}m ago`;
  if (ago < 86_400_000) return `${Math.floor(ago / 3_600_000)}h ago`;
  return `${Math.floor(ago / 86_400_000)}d ago`;
}

export default function SessionsPanel({ serverId, workerUser }: SessionsPanelProps) {
  const [sessions, setSessions] = useState<CliSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState<string | null>(null); // "claude" | "codex" | null
  const [formUser, setFormUser] = useState<string>(workerUser || "root");
  const [formDisplayName, setFormDisplayName] = useState("");
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [attachedSession, setAttachedSession] = useState<string | null>(null);
  const [chatSession, setChatSession] = useState<number | null>(null);
  const toast = useToast();
  const confirm = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listServerSessions(serverId);
      setSessions(data.filter((s) => s.status !== "closed"));
    } catch {
      // ignore load errors
    } finally {
      setLoading(false);
    }
  }, [serverId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async () => {
    if (!creating) return;
    setFormSubmitting(true);
    try {
      const body: CliSessionCreate = {
        workspace_server_id: serverId,
        agent_name: creating,
        user_context: formUser,
        display_name: formDisplayName || undefined,
      };
      const session = await createSession(body);
      toast.success(`${creating} session started`);
      setCreating(null);
      setFormDisplayName("");
      setSessions((prev) => [session, ...prev]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create session");
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleClose = async (session: CliSession) => {
    const ok = await confirm({
      title: "End Session",
      message: `End ${session.agent_name} session ${session.display_name || session.session_id.slice(0, 8)}? This will kill the tmux session.`,
      confirmLabel: "End Session",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await closeSession(session.id);
      toast.success("Session ended");
      setSessions((prev) => prev.filter((s) => s.id !== session.id));
      if (attachedSession === session.session_id) setAttachedSession(null);
      if (chatSession === session.id) setChatSession(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to end session");
    }
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-300 inline-flex items-center gap-1.5">
          <Monitor className="w-3.5 h-3.5" />
          Sessions
          {sessions.length > 0 && (
            <span className="text-gray-500">({sessions.length})</span>
          )}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => { setCreating("claude"); setFormUser(workerUser || "root"); }}
            className="text-xs px-2 py-1 bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-300 rounded transition-colors inline-flex items-center gap-1"
          >
            <Plus className="w-3 h-3" />
            Claude
          </button>
          <button
            onClick={() => { setCreating("codex"); setFormUser(workerUser || "root"); }}
            className="text-xs px-2 py-1 bg-green-600/20 hover:bg-green-600/30 border border-green-500/30 text-green-300 rounded transition-colors inline-flex items-center gap-1"
          >
            <Plus className="w-3 h-3" />
            Codex
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="text-xs text-gray-500 hover:text-gray-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* New session form */}
      {creating && (
        <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3 space-y-2 animate-fade-in">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-200">
              New {creating} session
            </span>
            <button
              onClick={() => setCreating(null)}
              className="text-gray-500 hover:text-gray-300 p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={formUser}
              onChange={(e) => setFormUser(e.target.value)}
              className="text-xs px-2 py-1 bg-gray-800 border border-gray-700 rounded text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
            >
              <option value="root">root</option>
              {workerUser && <option value={workerUser}>{workerUser}</option>}
            </select>
            <input
              type="text"
              value={formDisplayName}
              onChange={(e) => setFormDisplayName(e.target.value)}
              placeholder="Display name (optional)"
              className="flex-1 min-w-[140px] px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
            />
            <button
              onClick={handleCreate}
              disabled={formSubmitting}
              className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded transition-colors inline-flex items-center gap-1"
            >
              {formSubmitting && <Loader2 className="w-3 h-3 animate-spin" />}
              Start
            </button>
          </div>
        </div>
      )}

      {/* Session list */}
      {sessions.length === 0 && !loading && (
        <p className="text-xs text-gray-500 py-2">No active sessions.</p>
      )}
      {loading && sessions.length === 0 && (
        <div className="flex items-center gap-2 text-gray-500 text-xs py-2">
          <Loader2 className="w-3 h-3 animate-spin" />
          Loading sessions...
        </div>
      )}
      {sessions.map((s) => (
        <div key={s.id} className="space-y-0">
          <div className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-gray-800/30 group/row">
            {/* Status dot */}
            <span className={`w-2 h-2 rounded-full shrink-0 ${statusDotColor(s.status)}`} />

            {/* Agent badge */}
            <span
              className={`text-xs font-mono px-1.5 py-0.5 rounded shrink-0 ${
                s.agent_name === "claude"
                  ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                  : "bg-green-500/10 text-green-400 border border-green-500/20"
              }`}
            >
              {s.agent_name}
            </span>

            {/* Name / ID */}
            <span className="text-xs text-gray-200 truncate max-w-[120px]" title={s.session_id}>
              {s.display_name || s.session_id.slice(0, 8)}
            </span>

            {/* User */}
            <span className="text-xs text-gray-500 font-mono shrink-0">
              {s.user_context}
            </span>

            {/* Last activity */}
            <span className="text-xs text-gray-600 shrink-0 ml-auto mr-2">
              {relativeTime(s.last_activity_at)}
            </span>

            {/* Actions */}
            <div className="flex items-center gap-0.5 opacity-60 group-hover/row:opacity-100 transition-opacity shrink-0">
              <button
                onClick={() =>
                  setAttachedSession(
                    attachedSession === s.session_id ? null : s.session_id,
                  )
                }
                className={`text-xs inline-flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors ${
                  attachedSession === s.session_id
                    ? "text-orange-400 hover:text-orange-300 hover:bg-orange-900/20"
                    : "text-gray-400 hover:text-white hover:bg-gray-700/50"
                }`}
                title={attachedSession === s.session_id ? "Detach" : "Attach terminal"}
              >
                <SquareTerminal className="w-3 h-3" />
                {attachedSession === s.session_id ? "Detach" : "Attach"}
              </button>
              {s.agent_name === "claude" && s.remote_control_enabled && (
                <button
                  onClick={() =>
                    setChatSession(chatSession === s.id ? null : s.id)
                  }
                  className={`text-xs inline-flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors ${
                    chatSession === s.id
                      ? "text-blue-400 hover:text-blue-300 hover:bg-blue-900/20"
                      : "text-gray-400 hover:text-white hover:bg-gray-700/50"
                  }`}
                  title="Chat interface"
                >
                  <MessageSquare className="w-3 h-3" />
                  Chat
                </button>
              )}
              <button
                onClick={() => handleClose(s)}
                className="text-xs text-red-400 hover:text-red-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-red-900/20 transition-colors"
                title="End session"
              >
                <X className="w-3 h-3" />
                End
              </button>
            </div>
          </div>

          {/* Inline terminal */}
          {attachedSession === s.session_id && (
            <div className="ml-4 mt-1 mb-2 animate-fade-in">
              <TerminalPanel
                serverId={serverId}
                sessionId={s.session_id}
                key={`session-term-${s.session_id}`}
              />
            </div>
          )}

          {/* Inline chat */}
          {chatSession === s.id && (
            <div className="ml-4 mt-1 mb-2 animate-fade-in">
              <ChatPanel sessionId={s.id} key={`session-chat-${s.id}`} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
