// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { Bot, Loader2, MessageSquare, Plus, Send, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

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

const AGENTS = ["claude", "opencode", "gemini", "aider", "codex"];

export default function Chat() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState("claude");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/chat/sessions");
      if (res.ok) setSessions(await res.json());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession?.messages]);

  const createSession = async () => {
    setCreating(true);
    try {
      const res = await fetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_name: selectedAgent }),
      });
      if (res.ok) {
        const session = await res.json();
        setSessions((prev) => [session, ...prev]);
        setActiveSession(session);
      }
    } catch {
      /* ignore */
    } finally {
      setCreating(false);
    }
  };

  const loadSession = async (sessionId: string) => {
    try {
      const res = await fetch(`/api/chat/sessions/${sessionId}`);
      if (res.ok) {
        const session = await res.json();
        setActiveSession(session);
      }
    } catch {
      /* ignore */
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || !activeSession || loading) return;
    const msg = input.trim();
    setInput("");

    // Optimistic update
    const userMsg: ChatMessage = { role: "user", content: msg, timestamp: new Date().toISOString() };
    setActiveSession((prev) =>
      prev ? { ...prev, messages: [...prev.messages, userMsg] } : prev,
    );

    setLoading(true);
    try {
      const res = await fetch(`/api/chat/sessions/${activeSession.session_id}/message`, {
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
        setActiveSession((prev) =>
          prev ? { ...prev, messages: [...prev.messages, assistantMsg] } : prev,
        );
      }
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  const deleteSession = async (sessionId: string) => {
    await fetch(`/api/chat/sessions/${sessionId}`, { method: "DELETE" });
    setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    if (activeSession?.session_id === sessionId) setActiveSession(null);
  };

  return (
    <div className="flex h-[calc(100vh-5rem)] -mx-4 sm:-mx-6 lg:-mx-8 -my-6">
      {/* Sidebar */}
      {sidebarOpen && (
        <div className="w-72 border-r border-gray-800 bg-gray-900/50 flex flex-col">
          <div className="p-4 border-b border-gray-800">
            <div className="flex items-center gap-2 mb-3">
              <select
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
                className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              >
                {AGENTS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
              <button
                onClick={createSession}
                disabled={creating}
                className="p-1.5 rounded bg-cyan-600/20 text-cyan-400 hover:bg-cyan-600/30 disabled:opacity-50"
                title="New chat"
              >
                {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {sessions.map((s) => (
              <div
                key={s.session_id}
                className={`flex items-center gap-2 px-4 py-3 cursor-pointer hover:bg-gray-800/50 border-b border-gray-800/50 ${
                  activeSession?.session_id === s.session_id ? "bg-gray-800/70" : ""
                }`}
                onClick={() => loadSession(s.session_id)}
              >
                <MessageSquare className="w-4 h-4 text-gray-500 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-300 truncate">{s.display_name}</p>
                  <p className="text-xs text-gray-500">{s.agent_name}</p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(s.session_id);
                  }}
                  className="p-1 rounded hover:bg-red-900/30 text-gray-600 hover:text-red-400"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {sessions.length === 0 && (
              <p className="text-sm text-gray-500 text-center mt-8 px-4">
                No conversations yet. Select an agent and click + to start.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 bg-gray-900/30">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1 rounded hover:bg-gray-800 text-gray-400"
          >
            {sidebarOpen ? <X className="w-4 h-4" /> : <MessageSquare className="w-4 h-4" />}
          </button>
          {activeSession ? (
            <>
              <Bot className="w-5 h-5 text-cyan-400" />
              <span className="text-sm font-medium text-gray-200">{activeSession.display_name}</span>
              <span className="text-xs text-gray-500">({activeSession.agent_name})</span>
            </>
          ) : (
            <span className="text-sm text-gray-400">Select or create a conversation</span>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {!activeSession && (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <Bot className="w-12 h-12 mb-4 text-gray-600" />
              <p className="text-lg font-medium">AgenticKode Chat</p>
              <p className="text-sm mt-1">Chat with an AI agent to control the platform</p>
              <p className="text-xs mt-3 text-gray-600 max-w-md text-center">
                Create projects, launch tasks, monitor runs, approve PRs — all through natural conversation.
              </p>
            </div>
          )}

          {activeSession?.messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${
                  msg.role === "user"
                    ? "bg-cyan-600/20 text-gray-200 border border-cyan-600/30"
                    : msg.role === "system"
                      ? "bg-red-900/20 text-red-300 border border-red-700/30"
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

        {/* Input */}
        {activeSession && (
          <div className="border-t border-gray-800 px-4 py-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                placeholder="Ask the agent to do something..."
                disabled={loading}
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder-gray-500 disabled:opacity-50"
              />
              <button
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className="px-4 py-2.5 rounded-lg bg-cyan-600 text-white text-sm font-medium hover:bg-cyan-500 disabled:opacity-50 disabled:hover:bg-cyan-600"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
