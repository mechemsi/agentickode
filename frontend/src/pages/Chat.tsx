// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import {
  Bot,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  SquareTerminal,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
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

type Mode = "terminal" | "chat";

const AGENTS = ["claude", "opencode", "gemini", "aider", "codex"];

// ─── Component ──────────────────────────────────────────────────────
export default function Chat() {
  const [mode, setMode] = useState<Mode>("terminal");
  const [selectedAgent, setSelectedAgent] = useState("claude");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Terminal mode — each agent gets a live session key to force remount
  const [terminalKey, setTerminalKey] = useState(0);
  const [terminalActive, setTerminalActive] = useState(false);

  // Chat mode state
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [activeChatSession, setActiveChatSession] = useState<ChatSession | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ─── Data fetching ────────────────────────────────────────────────
  const fetchChatSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/chat/sessions");
      if (res.ok) setChatSessions(await res.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchChatSessions();
  }, [fetchChatSessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChatSession?.messages]);

  // ─── Terminal mode actions ────────────────────────────────────────
  const launchTerminal = () => {
    setTerminalKey((k) => k + 1);
    setTerminalActive(true);
  };

  const closeTerminal = () => {
    setTerminalActive(false);
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
      }
    } catch { /* ignore */ }
    finally { setCreating(false); }
  };

  const loadChatSession = async (sessionId: string) => {
    try {
      const res = await fetch(`/api/chat/sessions/${sessionId}`);
      if (res.ok) setActiveChatSession(await res.json());
    } catch { /* ignore */ }
  };

  const deleteChatSession = async (sessionId: string) => {
    await fetch(`/api/chat/sessions/${sessionId}`, { method: "DELETE" });
    setChatSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    if (activeChatSession?.session_id === sessionId) setActiveChatSession(null);
  };

  const sendMessage = async () => {
    if (!input.trim() || !activeChatSession || loading) return;
    const msg = input.trim();
    setInput("");

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
          content: data.response,
          timestamp: new Date().toISOString(),
        };
        setActiveChatSession((prev) =>
          prev ? { ...prev, messages: [...prev.messages, assistantMsg] } : prev,
        );
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
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
                {AGENTS.map((a) => (
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

          {/* Info panel (terminal mode) */}
          {mode === "terminal" && (
            <div className="flex-1 overflow-y-auto p-3">
              <div className="text-xs text-gray-500 space-y-2">
                <p>Terminal mode runs the agent <strong>locally</strong> inside the platform container.</p>
                <p>You get the full interactive experience — see tool calls, file edits, thinking in real-time.</p>
                <p className="text-gray-600">The agent has access to platform MCP tools for managing projects, runs, and servers.</p>
              </div>
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
                {terminalActive ? `${selectedAgent} (interactive)` : "Interactive Agent Terminal"}
              </span>
              {terminalActive && (
                <button
                  onClick={closeTerminal}
                  className="ml-auto text-xs px-2 py-1 rounded bg-red-600/20 text-red-400 hover:bg-red-600/30"
                >
                  End Session
                </button>
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
        <div className="flex-1 overflow-hidden">
          {mode === "terminal" ? (
            terminalActive ? (
              <div className="h-full">
                <LocalTerminal key={terminalKey} agentName={selectedAgent} />
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <SquareTerminal className="w-12 h-12 mb-4 text-gray-600" />
                <p className="text-lg font-medium">Interactive Agent Terminal</p>
                <p className="text-sm mt-1">Full Claude Code experience in the browser</p>
                <p className="text-xs mt-3 text-gray-600 max-w-md text-center">
                  Select an agent and click Launch to start an interactive session.
                  See everything — tool calls, file edits, thinking — live.
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
