---
title: 8-Bit Agent Office — Implementation Plan
status: in-progress
date: 2026-04-01
related: [docs/plans/2026-04-01-8bit-agent-office-design.md]
---

# 8-Bit Agent Office Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an 8-bit pixel art office modal showing live agent activity across workspace servers, accessible from the nav bar.

**Architecture:** Backend adds a `/ws/office` WebSocket that aggregates server/session/run state into spatial office events. Frontend uses PixiJS inside a React modal to render rooms, agent sprites, and animations. Existing Broadcaster singleton gets an office subscriber type.

**Tech Stack:** Python/FastAPI (backend WS), PixiJS + @pixi/react (canvas), React (modal/tooltip/controls), existing WebSocket infrastructure.

---

## Stream A: Backend (independent — can run in parallel with Stream B scaffolding)

### Task A1: Add office subscriber type to Broadcaster

**Files:**
- Modify: `backend/worker/broadcaster.py`

**Step 1: Add office subscriber list and methods**

Add to `Broadcaster.__init__`:
```python
self._office_subs: list[asyncio.Queue] = []
```

Add methods after `unsubscribe_global`:
```python
def subscribe_office(self, queue: asyncio.Queue):
    self._office_subs.append(queue)

def unsubscribe_office(self, queue: asyncio.Queue):
    self._office_subs = [q for q in self._office_subs if q is not queue]
```

**Step 2: Fan out global events to office subscribers**

In the `event()` method, after the global subscriber loop, add:
```python
for q in self._office_subs:
    with contextlib.suppress(asyncio.QueueFull):
        q.put_nowait(payload)
```

**Step 3: Commit**
```bash
git add backend/worker/broadcaster.py
git commit -m "feat(office): add office subscriber type to Broadcaster"
```

---

### Task A2: Create ws_office.py WebSocket endpoint

**Files:**
- Create: `backend/api/ws_office.py`

**Full implementation:**

```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""WebSocket endpoint for the 8-bit Agent Office live view."""

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.database import async_session
from backend.models import CliSession, TaskRun, WorkspaceServer
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("agentickode.ws_office")
router = APIRouter()

# Phase name → office activity mapping
_PHASE_ACTIVITY = {
    "workspace_setup": "starting",
    "init": "starting",
    "planning": "planning",
    "coding": "coding",
    "testing": "testing",
    "reviewing": "reviewing",
    "approval": "idle",
    "finalization": "coding",
}


def _run_to_agent(run: TaskRun) -> dict | None:
    """Convert a running TaskRun to an office agent dict."""
    if run.status not in ("running", "pending"):
        return None
    phase = run.current_phase or "init"
    activity = _PHASE_ACTIVITY.get(phase, "coding")
    return {
        "id": f"run-{run.id}",
        "agent_type": run.agent_name or "generic",
        "room_id": run.workspace_server_id or "platform",
        "desk": None,  # assigned by client
        "status": "active" if run.status == "running" else "starting",
        "activity": activity,
        "project": run.project_slug or "",
        "phase": phase,
        "run_id": run.id,
        "display_name": f"Run #{run.id}",
    }


def _session_to_agent(sess: CliSession) -> dict | None:
    """Convert a CliSession to an office agent dict."""
    if sess.status in ("closed", "error"):
        return None
    activity = "coding" if sess.status == "active" else "idle" if sess.status == "idle" else "starting"
    return {
        "id": f"session-{sess.session_id}",
        "agent_type": sess.agent_name or "generic",
        "room_id": sess.workspace_server_id or "platform",
        "desk": None,
        "status": sess.status,
        "activity": activity,
        "project": "",
        "phase": "session",
        "run_id": None,
        "display_name": sess.display_name or sess.agent_name or "Agent",
    }


async def _build_initial_state() -> dict:
    """Build the full office state snapshot."""
    async with async_session() as session:
        # Fetch servers
        result = await session.execute(select(WorkspaceServer))
        servers = result.scalars().all()

        # Fetch active runs
        result = await session.execute(
            select(TaskRun).where(TaskRun.status.in_(["running", "pending"]))
        )
        runs = result.scalars().all()

        # Fetch active sessions
        result = await session.execute(
            select(CliSession).where(CliSession.status.in_(["starting", "active", "idle", "detached"]))
        )
        sessions = result.scalars().all()

    rooms = [{"id": "platform", "name": "Platform", "status": "online", "capacity": None}]
    for s in servers:
        rooms.append({
            "id": s.id,
            "name": s.name,
            "status": s.status or "unknown",
            "capacity": s.max_concurrent_tasks or 4,
        })

    agents = []
    for r in runs:
        agent = _run_to_agent(r)
        if agent:
            agents.append(agent)
    for s in sessions:
        agent = _session_to_agent(s)
        if agent:
            agents.append(agent)

    return {"type": "office_state", "rooms": rooms, "agents": agents}


def _translate_event(event: dict) -> dict | None:
    """Translate a Broadcaster global event into an office-specific event."""
    etype = event.get("type")
    run_id = event.get("run_id")

    if etype == "run_created":
        return {
            "type": "agent_spawned",
            "agent": {
                "id": f"run-{run_id}",
                "agent_type": event.get("agent_name", "generic"),
                "status": "starting",
                "activity": "starting",
                "project": event.get("project_slug", ""),
                "phase": "init",
                "run_id": run_id,
                "display_name": f"Run #{run_id}",
            },
            "room_id": "platform",
        }

    if etype == "phase_changed":
        phase = event.get("phase", "coding")
        activity = _PHASE_ACTIVITY.get(phase, "coding")
        server_id = event.get("workspace_server_id")
        if server_id:
            return {
                "type": "agent_moving",
                "agent_id": f"run-{run_id}",
                "from": "platform",
                "to": server_id,
                "activity": activity,
                "phase": phase,
            }
        return {
            "type": "activity_changed",
            "agent_id": f"run-{run_id}",
            "activity": activity,
            "phase": phase,
        }

    if etype == "status_changed":
        new_status = event.get("status")
        if new_status == "failed":
            return {
                "type": "agent_error",
                "agent_id": f"run-{run_id}",
                "error": event.get("error", "failed"),
            }
        if new_status in ("completed", "cancelled"):
            return {
                "type": "agent_finished",
                "agent_id": f"run-{run_id}",
            }

    return None


@router.websocket("/ws/office")
async def ws_office(websocket: WebSocket):
    """Stream office state and live agent events for the 8-bit office view."""
    await websocket.accept()
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
    broadcaster.subscribe_office(queue)
    try:
        # Send initial state
        state = await _build_initial_state()
        await websocket.send_text(json.dumps(state, default=str))

        # Stream events
        while True:
            event = await queue.get()
            office_event = _translate_event(event)
            if office_event:
                await websocket.send_text(json.dumps(office_event, default=str))
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe_office(queue)
```

**Step 2: Commit**
```bash
git add backend/api/ws_office.py
git commit -m "feat(office): add /ws/office WebSocket endpoint"
```

---

### Task A3: Register the office WebSocket route in main.py

**Files:**
- Modify: `backend/main.py`

**Step 1: Add import**

After `from backend.api import ... ws,` add:
```python
from backend.api import ws_office,
```

Actually, add `ws_office` to the existing import block near line 54.

**Step 2: Register router**

After line 413 (`app.include_router(ws.router)`), add:
```python
app.include_router(ws_office.router)
```

**Step 3: Commit**
```bash
git add backend/main.py
git commit -m "feat(office): register /ws/office route"
```

---

## Stream B: Frontend — Scaffolding & PixiJS Setup

### Task B1: Install PixiJS dependencies

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install packages**
```bash
docker compose -f docker-compose.dev.yml exec frontend npm install pixi.js @pixi/react
```

**Step 2: Commit**
```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat(office): add pixi.js and @pixi/react dependencies"
```

---

### Task B2: Create useOfficeSocket hook

**Files:**
- Create: `frontend/src/hooks/useOfficeSocket.ts`

```typescript
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

      // Notify canvas callbacks
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
```

**Step 2: Commit**
```bash
git add frontend/src/hooks/useOfficeSocket.ts
git commit -m "feat(office): add useOfficeSocket WebSocket hook"
```

---

### Task B3: Create OfficeModal and OfficeIcon components

**Files:**
- Create: `frontend/src/components/office/OfficeModal.tsx`
- Create: `frontend/src/components/office/OfficeIcon.tsx`

**OfficeIcon.tsx** — The nav button:
```typescript
// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from 'react';
import OfficeModal from './OfficeModal';

export default function OfficeIcon() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="relative px-2 py-1.5 rounded text-gray-400 hover:text-white hover:bg-gray-800/50 text-xs font-mono tracking-tight"
        title="Agent Office"
      >
        <span className="inline-block" style={{ imageRendering: 'pixelated', fontSize: '16px', lineHeight: 1 }}>
          🏢
        </span>
      </button>
      {open && <OfficeModal onClose={() => setOpen(false)} />}
    </>
  );
}
```

**OfficeModal.tsx** — Modal container with PixiJS canvas:
```typescript
// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useRef, useCallback } from 'react';
import { useOfficeSocket } from '../../hooks/useOfficeSocket';
import type { OfficeAgent } from '../../hooks/useOfficeSocket';
import OfficeCanvas from './OfficeCanvas';

interface Props {
  onClose: () => void;
}

export default function OfficeModal({ onClose }: Props) {
  const { rooms, agents, connected, onEvent } = useOfficeSocket(true);
  const backdropRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === backdropRef.current) onClose();
  };

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
    >
      <div className="relative w-[95vw] h-[90vh] bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {/* Header */}
        <div className="absolute top-0 left-0 right-0 h-10 bg-gray-900/90 border-b border-gray-800 flex items-center px-4 z-10">
          <span className="text-sm font-mono text-gray-300">
            Agent Office
            {connected
              ? <span className="ml-2 text-green-400 text-xs">● connected</span>
              : <span className="ml-2 text-red-400 text-xs">● disconnected</span>
            }
          </span>
          <span className="ml-4 text-xs text-gray-500">
            {agents.size} agent{agents.size !== 1 ? 's' : ''} active
          </span>
          <button
            onClick={onClose}
            className="ml-auto text-gray-400 hover:text-white text-sm"
          >
            ESC
          </button>
        </div>

        {/* Canvas */}
        <div className="pt-10 w-full h-full">
          <OfficeCanvas rooms={rooms} agents={agents} onEvent={onEvent} />
        </div>
      </div>
    </div>
  );
}
```

**Step 3: Commit**
```bash
git add frontend/src/components/office/
git commit -m "feat(office): add OfficeModal and OfficeIcon components"
```

---

### Task B4: Create OfficeCanvas with PixiJS room rendering

**Files:**
- Create: `frontend/src/components/office/OfficeCanvas.tsx`

This is the core rendering component. Uses PixiJS Application directly (not @pixi/react declarative API, which is unstable) via a ref-based approach.

```typescript
// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useRef } from 'react';
import { Application, Container, Graphics, Text, TextStyle } from 'pixi.js';
import type { OfficeRoom, OfficeAgent, OfficeEvent } from '../../hooks/useOfficeSocket';

// Layout constants
const ROOM_PADDING = 16;
const DESK_SIZE = 24;
const DESK_GAP = 8;
const ROOM_HEADER = 28;
const AGENT_SIZE = 16;
const SCALE = 3;

// Colors per agent type
const AGENT_COLORS: Record<string, number> = {
  claude: 0x9F7AEA,    // purple
  codex: 0x48BB78,     // green
  aider: 0x4299E1,     // blue
  ollama: 0xED8936,    // orange
  openhands: 0xFC8181, // red-orange
  generic: 0xA0AEC0,   // gray
};

// Activity colors (glow around agent)
const ACTIVITY_COLORS: Record<string, number> = {
  coding: 0x48BB78,
  planning: 0x4299E1,
  reviewing: 0xECC94B,
  testing: 0xED8936,
  idle: 0x718096,
  starting: 0x4299E1,
  error: 0xFC5185,
};

interface RoomLayout {
  x: number;
  y: number;
  width: number;
  height: number;
  desks: Array<{ x: number; y: number; occupied: string | null }>;
  container: Container;
}

interface AgentSprite {
  container: Container;
  body: Graphics;
  glow: Graphics;
  label: Text;
  targetX: number;
  targetY: number;
}

interface Props {
  rooms: Map<string | number, OfficeRoom>;
  agents: Map<string, OfficeAgent>;
  onEvent: (cb: (event: OfficeEvent) => void) => () => void;
}

export default function OfficeCanvas({ rooms, agents, onEvent }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<Application | null>(null);
  const roomLayoutsRef = useRef<Map<string | number, RoomLayout>>(new Map());
  const agentSpritesRef = useRef<Map<string, AgentSprite>>(new Map());
  const stageRef = useRef<Container | null>(null);

  // Initialize PixiJS app
  useEffect(() => {
    if (!containerRef.current) return;

    const app = new Application();
    const initPromise = app.init({
      resizeTo: containerRef.current,
      background: 0x0D1117,
      antialias: false,
      resolution: 1,
    }).then(() => {
      if (!containerRef.current) return;
      containerRef.current.appendChild(app.canvas as HTMLCanvasElement);
      appRef.current = app;
      stageRef.current = app.stage;
    });

    return () => {
      initPromise.then(() => {
        app.destroy(true);
        appRef.current = null;
        stageRef.current = null;
      });
    };
  }, []);

  // Render rooms when they change
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    // Clear old rooms
    for (const [, layout] of roomLayoutsRef.current) {
      stage.removeChild(layout.container);
    }
    roomLayoutsRef.current.clear();

    const roomArr = Array.from(rooms.values());
    const platformRoom = roomArr.find(r => r.id === 'platform');
    const serverRooms = roomArr.filter(r => r.id !== 'platform');

    let offsetX = ROOM_PADDING;
    const offsetY = ROOM_PADDING;

    // Draw platform room
    if (platformRoom) {
      const layout = drawRoom(stage, platformRoom, offsetX, offsetY, 6);
      roomLayoutsRef.current.set('platform', layout);
      offsetX += layout.width + ROOM_PADDING * 2;
    }

    // Draw server rooms in a grid
    const cols = Math.ceil(Math.sqrt(serverRooms.length));
    let col = 0;
    let row = 0;
    const gridStartX = offsetX;

    for (const room of serverRooms) {
      const capacity = room.capacity || 4;
      const x = gridStartX + col * (capacity * (DESK_SIZE + DESK_GAP) + ROOM_PADDING * 3);
      const y = offsetY + row * (200 + ROOM_PADDING);
      const layout = drawRoom(stage, room, x, y, capacity);
      roomLayoutsRef.current.set(room.id, layout);

      col++;
      if (col >= cols) {
        col = 0;
        row++;
      }
    }
  }, [rooms]);

  // Render agents when they change
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    // Remove agents that no longer exist
    for (const [id, sprite] of agentSpritesRef.current) {
      if (!agents.has(id)) {
        stage.removeChild(sprite.container);
        agentSpritesRef.current.delete(id);
      }
    }

    // Add/update agents
    for (const [id, agent] of agents) {
      const roomLayout = roomLayoutsRef.current.get(agent.room_id);
      if (!roomLayout) continue;

      // Find a desk
      let deskPos = roomLayout.desks.find(d => d.occupied === id);
      if (!deskPos) {
        deskPos = roomLayout.desks.find(d => d.occupied === null);
        if (deskPos) deskPos.occupied = id;
      }
      if (!deskPos) continue;

      let sprite = agentSpritesRef.current.get(id);
      if (!sprite) {
        sprite = createAgentSprite(stage, agent);
        agentSpritesRef.current.set(id, sprite);
      }

      // Update position target
      sprite.targetX = deskPos.x;
      sprite.targetY = deskPos.y - DESK_SIZE;

      // Update colors
      const color = AGENT_COLORS[agent.agent_type] || AGENT_COLORS.generic;
      const glowColor = ACTIVITY_COLORS[agent.activity] || ACTIVITY_COLORS.idle;
      sprite.body.clear();
      sprite.body.rect(-AGENT_SIZE / 2, -AGENT_SIZE / 2, AGENT_SIZE, AGENT_SIZE);
      sprite.body.fill(color);
      sprite.glow.clear();
      sprite.glow.circle(0, 0, AGENT_SIZE);
      sprite.glow.fill({ color: glowColor, alpha: 0.2 });

      // Snap position (animation can be added later)
      sprite.container.x = sprite.targetX;
      sprite.container.y = sprite.targetY;
    }
  }, [agents, rooms]);

  return <div ref={containerRef} className="w-full h-full" style={{ imageRendering: 'pixelated' }} />;
}

function drawRoom(
  stage: Container,
  room: OfficeRoom,
  x: number,
  y: number,
  capacity: number,
): RoomLayout {
  const container = new Container();
  container.x = x;
  container.y = y;

  const desksPerRow = Math.min(capacity, 3);
  const rows = Math.ceil(capacity / desksPerRow);
  const innerW = desksPerRow * (DESK_SIZE + DESK_GAP) + ROOM_PADDING;
  const innerH = ROOM_HEADER + rows * (DESK_SIZE * 2 + DESK_GAP) + ROOM_PADDING;

  const isOffline = room.status === 'offline';

  // Room background
  const bg = new Graphics();
  bg.roundRect(0, 0, innerW, innerH, 4);
  bg.fill(isOffline ? 0x1A1A2E : 0x161B22);
  bg.stroke({ color: isOffline ? 0x2D2D44 : 0x30363D, width: 1 });
  container.addChild(bg);

  // Room label
  const labelStyle = new TextStyle({
    fontFamily: '"Press Start 2P", monospace',
    fontSize: 8,
    fill: isOffline ? 0x4A5568 : 0xE2E8F0,
  });
  const label = new Text({ text: room.name, style: labelStyle });
  label.x = ROOM_PADDING / 2;
  label.y = 6;
  container.addChild(label);

  // Desks
  const desks: RoomLayout['desks'] = [];
  for (let i = 0; i < capacity; i++) {
    const col = i % desksPerRow;
    const row = Math.floor(i / desksPerRow);
    const dx = ROOM_PADDING / 2 + col * (DESK_SIZE + DESK_GAP);
    const dy = ROOM_HEADER + row * (DESK_SIZE * 2 + DESK_GAP);

    const desk = new Graphics();
    desk.rect(dx, dy, DESK_SIZE, DESK_SIZE);
    desk.fill(isOffline ? 0x2D2D44 : 0x21262D);
    desk.stroke({ color: 0x30363D, width: 1 });
    container.addChild(desk);

    desks.push({ x: x + dx + DESK_SIZE / 2, y: y + dy, occupied: null });
  }

  // Offline overlay
  if (isOffline) {
    const overlay = new Graphics();
    overlay.roundRect(0, 0, innerW, innerH, 4);
    overlay.fill({ color: 0x000000, alpha: 0.4 });
    container.addChild(overlay);
  }

  stage.addChild(container);

  return { x, y, width: innerW, height: innerH, desks, container };
}

function createAgentSprite(stage: Container, agent: OfficeAgent): AgentSprite {
  const container = new Container();

  const glow = new Graphics();
  const glowColor = ACTIVITY_COLORS[agent.activity] || ACTIVITY_COLORS.idle;
  glow.circle(0, 0, AGENT_SIZE);
  glow.fill({ color: glowColor, alpha: 0.2 });
  container.addChild(glow);

  const body = new Graphics();
  const color = AGENT_COLORS[agent.agent_type] || AGENT_COLORS.generic;
  body.rect(-AGENT_SIZE / 2, -AGENT_SIZE / 2, AGENT_SIZE, AGENT_SIZE);
  body.fill(color);
  container.addChild(body);

  const labelStyle = new TextStyle({
    fontFamily: '"Press Start 2P", monospace',
    fontSize: 6,
    fill: 0xFFFFFF,
  });
  const label = new Text({ text: agent.agent_type.slice(0, 5), style: labelStyle });
  label.anchor.set(0.5, 0);
  label.y = AGENT_SIZE / 2 + 2;
  container.addChild(label);

  stage.addChild(container);

  return { container, body, glow, label, targetX: 0, targetY: 0 };
}
```

**Step 2: Commit**
```bash
git add frontend/src/components/office/OfficeCanvas.tsx
git commit -m "feat(office): add PixiJS canvas with room/agent rendering"
```

---

### Task B5: Add OfficeIcon to Nav component

**Files:**
- Modify: `frontend/src/components/shared/Nav.tsx`

**Step 1: Import OfficeIcon**

After the lucide-react imports (line 20), add:
```typescript
import OfficeIcon from '../office/OfficeIcon';
```

**Step 2: Place it in the nav bar**

After the "New Run" button section (after line 76), before the mobile hamburger, add:
```tsx
<OfficeIcon />
```

Specifically, inside the `hidden md:flex ml-auto` div, before the closing `</div>`, add `<OfficeIcon />` so it sits next to "New Run".

**Step 3: Commit**
```bash
git add frontend/src/components/shared/Nav.tsx
git commit -m "feat(office): add office icon to nav bar"
```

---

### Task B6: Add Press Start 2P font

**Files:**
- Modify: `frontend/index.html`

**Step 1: Add Google Font link in `<head>`**

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
```

**Step 2: Commit**
```bash
git add frontend/index.html
git commit -m "feat(office): add Press Start 2P pixel font"
```

---

## Stream C: Tooltip & Control Panel (depends on B3, B4)

### Task C1: Create OfficeTooltip component

**Files:**
- Create: `frontend/src/components/office/OfficeTooltip.tsx`

Simple HTML overlay that positions itself over the canvas based on agent coordinates.

```typescript
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
```

---

### Task C2: Create OfficeControlPanel component

**Files:**
- Create: `frontend/src/components/office/OfficeControlPanel.tsx`

Click popover with mini terminal, kill, and navigate actions.

```typescript
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
        {/* Mini terminal */}
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

        {/* Actions */}
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
```

**Step 3: Commit both**
```bash
git add frontend/src/components/office/OfficeTooltip.tsx frontend/src/components/office/OfficeControlPanel.tsx
git commit -m "feat(office): add tooltip and control panel components"
```

---

## Dependency Graph

```
Stream A (backend):  A1 → A2 → A3  (sequential)
Stream B (frontend): B1 → B2 → B3 → B4 → B5 → B6  (sequential)
Stream C (controls): C1 + C2  (parallel, after B3)

A and B are fully independent — can run in parallel.
C depends on B3 being done (it imports types from useOfficeSocket).
```
