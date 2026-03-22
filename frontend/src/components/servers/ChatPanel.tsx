// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useRef, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { sendToSession, captureSession } from "../../api/sessions";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export default function ChatPanel({ sessionId }: { sessionId: number }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Capture initial output on mount
  useEffect(() => {
    captureSession(sessionId, 30)
      .then((res) => {
        if (res.output.trim()) {
          setMessages([{ role: "assistant", text: res.output.trim() }]);
        }
      })
      .catch(() => {
        // ignore initial capture failure
      });
  }, [sessionId]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const result = await sendToSession(sessionId, msg);
      // Brief delay then capture output for more complete response
      await new Promise((r) => setTimeout(r, 1500));
      const captured = await captureSession(sessionId, 30);
      const output = captured.output.trim() || result.output || "(no output)";
      setMessages((prev) => [...prev, { role: "assistant", text: output }]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Error: ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col rounded-lg border border-gray-700/50 bg-gray-950/40 overflow-hidden" style={{ height: 400 }}>
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && !loading && (
          <p className="text-xs text-gray-500 text-center mt-8">
            Send a message to interact with the CLI session.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-xs ${
                m.role === "user"
                  ? "bg-blue-600/20 border border-blue-500/30 text-blue-100"
                  : "bg-gray-800/60 border border-gray-700/40 text-gray-300"
              }`}
            >
              <pre className="whitespace-pre-wrap break-all font-mono leading-relaxed">
                {m.text}
              </pre>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800/60 border border-gray-700/40 rounded-lg px-3 py-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-gray-700/50 p-2 flex items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Type a message..."
          disabled={loading}
          className="flex-1 px-3 py-1.5 bg-gray-800/80 border border-gray-700/50 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          className="p-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded transition-colors"
          title="Send"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
