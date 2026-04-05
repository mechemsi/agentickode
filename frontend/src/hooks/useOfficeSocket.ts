// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useRef, useCallback, useState } from 'react';

export interface OfficeRoom {
  id: string | number;
  name: string;
  status: string;
  capacity: number | null;
}

export interface OfficeAgent {
  id: string;
  agent_type: string;
  room_id: string | number;
  desk: number | null;
  status: string;
  activity: string;
  project: string;
  phase: string;
  run_id: number | null;
  display_name: string;
}

export type OfficeEvent =
  | { type: 'office_state'; rooms: OfficeRoom[]; agents: OfficeAgent[] }
  | { type: 'agent_spawned'; agent: OfficeAgent; room_id: string | number }
  | { type: 'agent_moving'; agent_id: string; from: string | number; to: string | number; activity: string; phase: string }
  | { type: 'agent_seated'; agent_id: string; room_id: string | number; desk: number; activity: string }
  | { type: 'activity_changed'; agent_id: string; activity: string; phase: string }
  | { type: 'agent_error'; agent_id: string; error: string }
  | { type: 'agent_finished'; agent_id: string }
  | { type: 'agent_left'; agent_id: string }
  | { type: 'room_status'; room_id: string | number; status: string };

interface OfficeState {
  rooms: Map<string | number, OfficeRoom>;
  agents: Map<string, OfficeAgent>;
  connected: boolean;
}

export function useOfficeSocket(enabled: boolean) {
  const [state, setState] = useState<OfficeState>({
    rooms: new Map(),
    agents: new Map(),
    connected: false,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const eventCallbacksRef = useRef<Array<(event: OfficeEvent) => void>>([]);

  const onEvent = useCallback((cb: (event: OfficeEvent) => void) => {
    eventCallbacksRef.current.push(cb);
    return () => {
      eventCallbacksRef.current = eventCallbacksRef.current.filter(c => c !== cb);
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/office`);
    wsRef.current = ws;

    ws.onopen = () => {
      setState(prev => ({ ...prev, connected: true }));
    };

    ws.onmessage = (e) => {
      const event: OfficeEvent = JSON.parse(e.data);

      for (const cb of eventCallbacksRef.current) {
        cb(event);
      }

      setState(prev => {
        const rooms = new Map(prev.rooms);
        const agents = new Map(prev.agents);

        switch (event.type) {
          case 'office_state':
            rooms.clear();
            agents.clear();
            for (const r of event.rooms) rooms.set(r.id, r);
            for (const a of event.agents) agents.set(a.id, a);
            break;

          case 'agent_spawned':
            agents.set(event.agent.id, event.agent);
            break;

          case 'agent_moving': {
            const agent = agents.get(event.agent_id);
            if (agent) {
              agents.set(event.agent_id, {
                ...agent,
                room_id: event.to,
                activity: event.activity,
                phase: event.phase,
              });
            }
            break;
          }

          case 'activity_changed': {
            const agent = agents.get(event.agent_id);
            if (agent) {
              agents.set(event.agent_id, {
                ...agent,
                activity: event.activity,
                phase: event.phase,
              });
            }
            break;
          }

          case 'agent_error': {
            const agent = agents.get(event.agent_id);
            if (agent) {
              agents.set(event.agent_id, { ...agent, status: 'error', activity: 'error' });
            }
            break;
          }

          case 'agent_finished':
          case 'agent_left':
            agents.delete(event.agent_id);
            break;

          case 'room_status': {
            const room = rooms.get(event.room_id);
            if (room) {
              rooms.set(event.room_id, { ...room, status: event.status });
            }
            break;
          }
        }

        return { rooms, agents, connected: true };
      });
    };

    ws.onclose = () => {
      setState(prev => ({ ...prev, connected: false }));
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [enabled]);

  return { ...state, onEvent };
}
