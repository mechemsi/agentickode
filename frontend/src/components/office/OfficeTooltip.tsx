// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type { OfficeAgent } from '../../hooks/useOfficeSocket';

interface Props {
  agent: OfficeAgent;
  x: number;
  y: number;
}

export default function OfficeTooltip({ agent, x, y }: Props) {
  return (
    <div
      className="absolute z-20 pointer-events-none bg-gray-900 border border-gray-700 rounded px-3 py-2 text-xs font-mono shadow-lg"
      style={{ left: x, top: y - 80, transform: 'translateX(-50%)' }}
    >
      <div className="text-white font-bold">{agent.display_name}</div>
      <div className="text-gray-400">Type: {agent.agent_type}</div>
      <div className="text-gray-400">Status: <span className={
        agent.activity === 'error' ? 'text-red-400' :
        agent.activity === 'idle' ? 'text-yellow-400' : 'text-green-400'
      }>{agent.activity}</span></div>
      {agent.phase && <div className="text-gray-400">Phase: {agent.phase}</div>}
      {agent.project && <div className="text-gray-400">Project: {agent.project}</div>}
      {agent.run_id && <div className="text-gray-400">Run: #{agent.run_id}</div>}
    </div>
  );
}
