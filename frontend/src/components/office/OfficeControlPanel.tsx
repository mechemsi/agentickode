// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { OfficeAgent } from '../../hooks/useOfficeSocket';
import { closeSession, sendToSession } from '../../api/sessions';

interface Props {
  agent: OfficeAgent;
  x: number;
  y: number;
  onClose: () => void;
}

export default function OfficeControlPanel({ agent, x, y, onClose }: Props) {
  const navigate = useNavigate();
  const [command, setCommand] = useState('');
  const [output, setOutput] = useState('');
  const [sending, setSending] = useState(false);

  const sessionId = agent.id.startsWith('session-')
    ? parseInt(agent.id.replace('session-', ''), 10)
    : null;

  const handleSend = async () => {
    if (!sessionId || !command.trim()) return;
    setSending(true);
    try {
      const res = await sendToSession(sessionId, command);
      setOutput(res.output || '(no output)');
      setCommand('');
    } catch {
      setOutput('Error sending command');
    } finally {
      setSending(false);
    }
  };

  const handleKill = async () => {
    if (!sessionId) return;
    try {
      await closeSession(sessionId);
      onClose();
    } catch {
      setOutput('Error closing session');
    }
  };

  return (
    <div
      className="absolute z-30 bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-72"
      style={{ left: x, top: y + 20, transform: 'translateX(-50%)' }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
        <span className="text-xs font-mono text-white">{agent.display_name}</span>
        <button onClick={onClose} className="text-gray-500 hover:text-white text-xs">✕</button>
      </div>

      <div className="p-2 space-y-2">
        {sessionId && (
          <div>
            <div className="bg-black rounded p-2 text-[10px] font-mono text-green-400 max-h-24 overflow-y-auto whitespace-pre-wrap">
              {output || 'Ready...'}
            </div>
            <div className="flex gap-1 mt-1">
              <input
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white font-mono"
                placeholder="command..."
                disabled={sending}
              />
              <button
                onClick={handleSend}
                disabled={sending}
                className="px-2 py-1 bg-blue-600 hover:bg-blue-500 rounded text-xs text-white disabled:opacity-50"
              >
                ⏎
              </button>
            </div>
          </div>
        )}

        <div className="flex gap-2">
          {agent.run_id && (
            <button
              onClick={() => { navigate(`/runs/${agent.run_id}`); onClose(); }}
              className="flex-1 px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-300"
            >
              View Run
            </button>
          )}
          {sessionId && (
            <button
              onClick={handleKill}
              className="flex-1 px-2 py-1 bg-red-900/50 hover:bg-red-800 rounded text-xs text-red-300"
            >
              Kill
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
