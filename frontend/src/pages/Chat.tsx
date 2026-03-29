// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import {
  AlertCircle,
  Bot,
  Check,
  Download,
  Loader2,
  MessageSquare,
  Pencil,
  Play,
  Plus,
  Send,
  SquareTerminal,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import LocalTerminal from "../components/chat/LocalTerminal";

// ─── Types ──────────────────────────────────────────────────────────
interface ChatSession {
  session_id: string;
  agent_name: string;
  display_name: string;
  status: string;
  messages: ChatMessage[];
  created_at: string | null;
  last_activity_at: string | null;
}

interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
}

interface AgentInfo {
  agent_name: string;
  enabled: boolean;
}

interface TerminalSession {
  id: number;
  session_id: string;
  agent_name: string;
  tmux_name: string;
  display_name: string | null;
  status: string;
  created_at: string;
  last_activity_at: string;
}

type Mode = "terminal" | "chat";

const FALLBACK_AGENTS = ["claude", "opencode", "gemini", "aider", "codex"];

// ─── Component ──────────────────────────────────────────────────────
const LAST_SESSION_KEY = "agentickode_last_chat_session";

export default function Chat() {
  const { sessionId: urlSessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>(urlSessionId ? "chat" : "terminal");
  const [selectedAgent, setSelectedAgent] = useState("claude");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [agents, setAgents] = useState<string[]>(FALLBACK_AGENTS);
  const [error, setError] = useState<string | null>(null);

  // Terminal mode — persistent sessions
  const [terminalSessions, setTerminalSessions] = useState<TerminalSession[]>([]);
  const [activeTerminal, setActiveTerminal] = useState<TerminalSession | null>(null);
  const [terminalKey, setTerminalKey] = useState(0);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // Chat mode state
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [activeChatSession, setActiveChatSession] = useState<ChatSession | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [setupNeeded, setSetupNeeded] = useState(false);
  const [runningSetup, setRunningSetup] = useState(false);
  const [setupLog, setSetupLog] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ─── Data fetching ────────────────────────────────────────────────
  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch("/api/agents");
      if (res.ok) {
        const data: AgentInfo[] = await res.json();
        const enabled = data.filter((a) => a.enabled).map((a) => a.agent_name);
        if (enabled.length > 0) setAgents(enabled);
      }
    } catch { /* use fallback */ }
  }, []);

  const fetchSetupStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/agent-setup/status");
      if (res.ok) {
        const data = await res.json();
        setSetupNeeded(data.needs_setup);
      }
    } catch { /* ignore */ }
  }, []);

  const runPostInstall = async () => {
    setRunningSetup(true);
    setSetupLog("Running post-install (plugins, marketplaces, skills)...\nThis may take several minutes.\n");
    try {
      const res = await fetch("/api/agent-setup/run-post-install", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setSetupLog((prev) => prev + "\n" + data.stdout + (data.stderr ? `\nErrors:\n${data.stderr}` : "") + `\nExit code: ${data.exit_code}`);
        if (data.exit_code === 0) setSetupNeeded(false);
      }
    } catch (e) {
      setSetupLog((prev) => prev + `\nFailed: ${e}`);
    } finally {
      setRunningSetup(false);
      fetchSetupStatus();
    }
  };

  const fetchChatSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/chat/sessions");
      if (res.ok) setChatSessions(await res.json());
    } catch { /* ignore */ }
  }, []);

  const fetchTerminalSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/local-terminals");
      if (res.ok) setTerminalSessions(await res.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchAgents();
    fetchChatSessions();
    fetchTerminalSessions();
    fetchSetupStatus();
  }, [fetchAgents, fetchChatSessions, fetchTerminalSessions, fetchSetupStatus]);

  // Auto-restore session from URL param or window.localStorage
  useEffect(() => {
    if (activeChatSession) return; // already have one
    const restoreId = urlSessionId || window.localStorage.getItem(LAST_SESSION_KEY);
    if (restoreId) {
      setMode("chat");
      loadChatSession(restoreId);
    }
  }, [urlSessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChatSession?.messages]);

  // ─── Terminal mode actions ────────────────────────────────────────
  const launchTerminal = async () => {
    setCreating(true);
    try {
      const res = await fetch("/api/local-terminals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_name: selectedAgent }),
      });
      if (res.ok) {
        const session: TerminalSession = await res.json();
        setTerminalSessions((prev) => [session, ...prev]);
        setActiveTerminal(session);
        setTerminalKey((k) => k + 1);
      }
    } catch { /* ignore */ }
    finally { setCreating(false); }
  };

  const resumeTerminal = (session: TerminalSession) => {
    setActiveTerminal(session);
    setTerminalKey((k) => k + 1);
  };

  const closeTerminal = async (sessionId: string) => {
    await fetch(`/api/local-terminals/${sessionId}`, { method: "DELETE" });
    setTerminalSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    if (activeTerminal?.session_id === sessionId) {
      setActiveTerminal(null);
    }
  };

  const renameTerminal = async (sessionId: string, displayName: string) => {
    const res = await fetch(`/api/local-terminals/${sessionId}/rename`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName }),
    });
    if (res.ok) {
      const updated: TerminalSession = await res.json();
      setTerminalSessions((prev) =>
        prev.map((s) => (s.session_id === sessionId ? updated : s)),
      );
      if (activeTerminal?.session_id === sessionId) {
        setActiveTerminal(updated);
      }
    }
    setRenamingId(null);
  };

  const resumeClosedTerminal = async (session: TerminalSession) => {
    setCreating(true);
    try {
      const res = await fetch(`/api/local-terminals/${session.session_id}/resume`, {
        method: "POST",
      });
      if (res.ok) {
        const resumed: TerminalSession = await res.json();
        setTerminalSessions((prev) =>
          prev.map((s) => (s.session_id === session.session_id ? resumed : s)),
        );
        setActiveTerminal(resumed);
        setTerminalKey((k) => k + 1);
      }
    } catch { /* ignore */ }
    finally { setCreating(false); }
  };

  // ─── Chat mode actions ────────────────────────────────────────────
  const createChatSession = async () => {
    setCreating(true);
    try {
      const res = await fetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_name: selectedAgent }),
      });
      if (res.ok) {
        const session = await res.json();
        setChatSessions((prev) => [session, ...prev]);
        setActiveChatSession(session);
        navigate(`/chat/${session.session_id}`, { replace: true });
        window.localStorage.setItem(LAST_SESSION_KEY, session.session_id);
      }
    } catch { /* ignore */ }
    finally { setCreating(false); }
  };

  const loadChatSession = async (sessionId: string) => {
    try {
      const res = await fetch(`/api/chat/sessions/${sessionId}`);
      if (res.ok) {
        const session = await res.json();
        setActiveChatSession(session);
        navigate(`/chat/${sessionId}`, { replace: true });
        window.localStorage.setItem(LAST_SESSION_KEY, sessionId);
      }
    } catch { /* ignore */ }
  };

  const deleteChatSession = async (sessionId: string) => {
    await fetch(`/api/chat/sessions/${sessionId}`, { method: "DELETE" });
    setChatSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    if (activeChatSession?.session_id === sessionId) {
      setActiveChatSession(null);
      navigate("/chat", { replace: true });
      window.localStorage.removeItem(LAST_SESSION_KEY);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || !activeChatSession || loading || sending) return;
    const msg = input.trim();
    setInput("");
    setError(null);
    setSending(true);

    const userMsg: ChatMessage = { role: "user", content: msg, timestamp: new Date().toISOString() };
    setActiveChatSession((prev) =>
      prev ? { ...prev, messages: [...prev.messages, userMsg] } : prev,
    );

    setLoading(true);
    try {
      const res = await fetch(`/api/chat/sessions/${activeChatSession.session_id}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      if (res.ok) {
        const data = await res.json();
        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: data.response || "(empty response)",
          timestamp: new Date().toISOString(),
        };
        setActiveChatSession((prev) =>
          prev ? { ...prev, messages: [...prev.messages, assistantMsg] } : prev,
        );
      } else {
        setError(`Agent error: ${res.status} ${res.statusText}`);
      }
    } catch (e) {
      setError(`Network error: ${e instanceof Error ? e.message : "connection failed"}`);
    } finally {
      setLoading(false);
      setSending(false);
    }
  };

  // ─── Render ───────────────────────────────────────────────────────
  return (
    <div className="flex h-[calc(100vh-5rem)] -mx-4 sm:-mx-6 lg:-mx-8 -my-6">
      {/* Sidebar */}
      {sidebarOpen && (
        <div className="w-72 border-r border-gray-800 bg-gray-900/50 flex flex-col">
          {/* Mode toggle */}
          <div className="p-3 border-b border-gray-800">
            <div className="flex bg-gray-800 rounded-lg p-0.5">
              <button
                onClick={() => setMode("terminal")}
                className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  mode === "terminal" ? "bg-cyan-600 text-white" : "text-gray-400 hover:text-gray-200"
                }`}
              >
                <SquareTerminal className="w-3.5 h-3.5" />
                Terminal
              </button>
              <button
                onClick={() => setMode("chat")}
                className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  mode === "chat" ? "bg-violet-600 text-white" : "text-gray-400 hover:text-gray-200"
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5" />
                Chat
              </button>
            </div>
          </div>

          {/* Agent selector + launch */}
          <div className="p-3 border-b border-gray-800">
            <div className="flex items-center gap-2 mb-2">
              <select
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
                className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              >
                {agents.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>

            <button
              onClick={mode === "terminal" ? launchTerminal : createChatSession}
              disabled={creating}
              className="w-full flex items-center justify-center gap-2 py-1.5 rounded bg-cyan-600/20 text-cyan-400 hover:bg-cyan-600/30 disabled:opacity-50 text-sm"
            >
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              {mode === "terminal" ? `Launch ${selectedAgent}` : "New Chat"}
            </button>

            {mode === "terminal" && setupNeeded && (
              <button
                onClick={runPostInstall}
                disabled={runningSetup}
                className="w-full flex items-center justify-center gap-2 py-1.5 rounded bg-amber-600/20 text-amber-400 hover:bg-amber-600/30 disabled:opacity-50 text-sm mt-2"
              >
                {runningSetup ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                {runningSetup ? "Installing..." : "Setup Plugins & Skills"}
              </button>
            )}
          </div>

          {/* Session list (chat mode only) */}
          {mode === "chat" && (
            <div className="flex-1 overflow-y-auto">
              {chatSessions.map((s) => (
                <div
                  key={s.session_id}
                  className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer hover:bg-gray-800/50 border-b border-gray-800/50 ${
                    activeChatSession?.session_id === s.session_id ? "bg-gray-800/70" : ""
                  }`}
                  onClick={() => loadChatSession(s.session_id)}
                >
                  <MessageSquare className="w-4 h-4 text-violet-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-300 truncate">{s.display_name}</p>
                    <p className="text-xs text-gray-500">{s.agent_name}</p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteChatSession(s.session_id); }}
                    className="p-1 rounded hover:bg-red-900/30 text-gray-600 hover:text-red-400"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
              {chatSessions.length === 0 && (
                <p className="text-sm text-gray-500 text-center mt-8 px-4">
                  No chat sessions yet.
                </p>
              )}
            </div>
          )}

          {/* Terminal session list */}
          {mode === "terminal" && (
            <div className="flex-1 overflow-y-auto">
              {setupLog && (
                <div className="p-3 border-b border-gray-800">
                  <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono bg-gray-900 rounded p-2 max-h-40 overflow-y-auto">
                    {setupLog}
                  </pre>
                </div>
              )}
              {/* Active sessions */}
              {terminalSessions.filter((s) => s.status === "active").length > 0 && (
                <div className="px-3 pt-2 pb-1">
                  <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Active</span>
                </div>
              )}
              {terminalSessions.filter((s) => s.status === "active").map((s) => (
                <div
                  key={s.session_id}
                  className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer hover:bg-gray-800/50 border-b border-gray-800/50 ${
                    activeTerminal?.session_id === s.session_id ? "bg-gray-800/70" : ""
                  }`}
                  onClick={() => resumeTerminal(s)}
                >
                  <SquareTerminal className="w-4 h-4 text-cyan-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    {renamingId === s.session_id ? (
                      <form
                        onSubmit={(e) => { e.preventDefault(); renameTerminal(s.session_id, renameValue); }}
                        className="flex items-center gap-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          autoFocus
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onBlur={() => setRenamingId(null)}
                          onKeyDown={(e) => e.key === "Escape" && setRenamingId(null)}
                          className="bg-gray-800 border border-gray-600 rounded px-1.5 py-0.5 text-xs text-gray-200 w-full"
                        />
                        <button type="submit" className="p-0.5 text-green-400 hover:text-green-300">
                          <Check className="w-3 h-3" />
                        </button>
                      </form>
                    ) : (
                      <>
                        <p className="text-sm text-gray-300 truncate">{s.display_name || s.agent_name}</p>
                        <p className="text-xs text-gray-500">{s.agent_name}</p>
                      </>
                    )}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); setRenamingId(s.session_id); setRenameValue(s.display_name || s.agent_name); }}
                    className="p-1 rounded hover:bg-gray-700 text-gray-600 hover:text-gray-300"
                    title="Rename"
                  >
                    <Pencil className="w-3 h-3" />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); closeTerminal(s.session_id); }}
                    className="p-1 rounded hover:bg-red-900/30 text-gray-600 hover:text-red-400"
                    title="End session"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
              {/* Closed sessions (resumable) */}
              {terminalSessions.filter((s) => s.status === "closed").length > 0 && (
                <>
                  <div className="px-3 pt-3 pb-1">
                    <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Closed (resumable)</span>
                  </div>
                  {terminalSessions.filter((s) => s.status === "closed").map((s) => (
                    <div
                      key={s.session_id}
                      className="flex items-center gap-2 px-3 py-2 hover:bg-gray-800/30 border-b border-gray-800/30"
                    >
                      <SquareTerminal className="w-4 h-4 text-gray-600 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-500 truncate">{s.display_name || s.agent_name}</p>
                        <p className="text-xs text-gray-600">{s.agent_name}</p>
                      </div>
                      <button
                        onClick={() => resumeClosedTerminal(s)}
                        disabled={creating}
                        className="p-1 rounded hover:bg-cyan-900/30 text-gray-500 hover:text-cyan-400 disabled:opacity-50"
                        title="Resume session"
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => closeTerminal(s.session_id)}
                        className="p-1 rounded hover:bg-red-900/30 text-gray-600 hover:text-red-400"
                        title="Remove session"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </>
              )}
              {terminalSessions.length === 0 && !setupLog && (
                <div className="text-xs text-gray-500 space-y-2 p-3">
                  <p>Terminal mode runs the agent <strong>locally</strong> inside the platform container.</p>
                  <p>Sessions persist — you can close the browser and resume later.</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Main area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 bg-gray-900/30">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1 rounded hover:bg-gray-800 text-gray-400"
          >
            {sidebarOpen ? <X className="w-4 h-4" /> : <MessageSquare className="w-4 h-4" />}
          </button>

          {mode === "terminal" ? (
            <>
              <SquareTerminal className="w-5 h-5 text-cyan-400" />
              <span className="text-sm font-medium text-gray-200">
                {activeTerminal ? (activeTerminal.display_name || activeTerminal.agent_name) : "Interactive Agent Terminal"}
              </span>
              {activeTerminal && (
                <>
                  <button
                    onClick={() => { setRenamingId(activeTerminal.session_id); setRenameValue(activeTerminal.display_name || activeTerminal.agent_name); }}
                    className="p-1 rounded hover:bg-gray-700 text-gray-500 hover:text-gray-300"
                    title="Rename session"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => closeTerminal(activeTerminal.session_id)}
                    className="ml-auto text-xs px-2 py-1 rounded bg-red-600/20 text-red-400 hover:bg-red-600/30"
                  >
                    End Session
                  </button>
                </>
              )}
            </>
          ) : activeChatSession ? (
            <>
              <Bot className="w-5 h-5 text-violet-400" />
              <span className="text-sm font-medium text-gray-200">{activeChatSession.display_name}</span>
              <span className="text-xs text-gray-500">({activeChatSession.agent_name})</span>
            </>
          ) : (
            <>
              <Bot className="w-5 h-5 text-gray-500" />
              <span className="text-sm text-gray-400">Select or create a chat session</span>
            </>
          )}
        </div>

        {/* Content */}
        {/* Error banner */}
        {error && (
          <div className="flex items-center gap-2 px-4 py-2 bg-red-900/30 border-b border-red-700/50 text-red-300 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        <div className="flex-1 overflow-hidden">
          {mode === "terminal" ? (
            activeTerminal ? (
              <div className="h-full">
                <LocalTerminal
                  key={terminalKey}
                  agentName={activeTerminal.agent_name}
                  tmuxName={activeTerminal.tmux_name}
                />
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <SquareTerminal className="w-12 h-12 mb-4 text-gray-600" />
                <p className="text-lg font-medium">Interactive Agent Terminal</p>
                <p className="text-sm mt-1">Full Claude Code experience in the browser</p>
                <p className="text-xs mt-3 text-gray-600 max-w-md text-center">
                  Select an agent and click Launch to start a persistent session.
                  Sessions survive page refresh — resume anytime from the sidebar.
                </p>
              </div>
            )
          ) : (
            <div className="h-full flex flex-col">
              <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                {!activeChatSession && (
                  <div className="flex flex-col items-center justify-center h-full text-gray-500">
                    <Bot className="w-12 h-12 mb-4 text-gray-600" />
                    <p className="text-lg font-medium">Platform Chat</p>
                    <p className="text-sm mt-1">Quick commands via MCP tools</p>
                  </div>
                )}

                {activeChatSession?.messages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${
                        msg.role === "user"
                          ? "bg-violet-600/20 text-gray-200 border border-violet-600/30"
                          : "bg-gray-800 text-gray-300 border border-gray-700"
                      }`}
                    >
                      <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>
                    </div>
                  </div>
                ))}

                {loading && (
                  <div className="flex justify-start">
                    <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5">
                      <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {activeChatSession && (
                <div className="border-t border-gray-800 px-4 py-3">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                      placeholder="Ask the agent..."
                      disabled={loading}
                      className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder-gray-500 disabled:opacity-50"
                    />
                    <button
                      onClick={sendMessage}
                      disabled={loading || !input.trim()}
                      className="px-4 py-2.5 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-500 disabled:opacity-50"
                    >
                      <Send className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
