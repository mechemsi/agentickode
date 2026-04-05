---
title: 8-Bit Agent Office — Live Monitoring Visualization
status: planned
date: 2026-04-01
related: []
---

# 8-Bit Agent Office — Live Monitoring Visualization

## Goal

Build an 8-bit pixel art office view that visualizes agent sessions across the platform and workspace servers in real time. Agents are represented as animated sprite characters that walk between rooms, work at desks, and reflect their actual status — providing both practical live monitoring and a fun ambient display.

## Scope

### In Scope
- Canvas-based 8-bit office rendered in a full-screen modal
- Animated character icon in the nav sidebar to open the office
- One room per workspace server + one platform room
- Distinct sprites per agent type (Claude, Codex, Aider, Ollama, OpenHands)
- Activity animations: coding, planning, reviewing, testing, idle/sleeping, error, walking
- Agents walk between rooms when delegating work
- Hover tooltips: agent name, status, phase, project, duration, tokens
- Click control panel: mini terminal, kill session, navigate to run detail
- Dedicated `/ws/office` WebSocket for real-time state
- Offline servers shown with "lights off" visual

### Out of Scope (future)
- Historical replay / time-lapse mode
- Sound effects
- Customizable office layouts
- Agent chat bubbles showing prompts/responses
- Mobile-optimized layout

## Technical Approach

### Frontend

**Stack**: PixiJS + `@pixi/react` for Canvas rendering inside a React modal.

**Component structure**:

```
frontend/src/components/office/
├── OfficeIcon.tsx          — Nav sidebar icon (animated tiny sprite, 24x24)
├── OfficeModal.tsx         — Full-screen modal container, manages lifecycle
├── OfficeCanvas.tsx        — PixiJS canvas, renders rooms + agents
├── OfficeTooltip.tsx       — HTML overlay positioned over canvas on hover
├── OfficeControlPanel.tsx  — Click popover: mini terminal, kill, navigate
├── sprites/                — Sprite sheet PNGs + animation definitions
│   ├── agents.png          — All agent type sprites
│   ├── furniture.png       — Desks, chairs, whiteboards
│   ├── rooms.png           — Floor tiles, walls, doors, hallways
│   └── effects.png         — Zzz bubbles, storm clouds, sparkles
└── useOfficeSocket.ts      — Hook: connects to ws/office, returns state
```

**State management**:
- `useOfficeSocket` hook manages the WebSocket connection
- Maintains `Map<agentId, AgentState>` and `Map<roomId, RoomState>`
- On `agent_moving` events, PixiJS tweens sprite along pre-calculated path between room doors
- On `activity_changed`, swap sprite animation frame sequence
- Hover detection via PixiJS `hitTest`, positions React tooltip at canvas coords

**Modal behavior**:
- Full-screen dark overlay with canvas centered
- ESC or click outside to close
- WebSocket connects on open, disconnects on close
- Canvas resizes responsively

### Backend

**New file: `backend/api/ws_office.py`** — WebSocket endpoint handler

On connect:
1. Query all workspace servers, active sessions, running task runs
2. Build initial `office_state` snapshot and send
3. Subscribe to Broadcaster events
4. Translate Broadcaster events into office-specific spatial events

Event translation:
- `run_created` → `agent_spawned` in platform room
- `phase_changed` with workspace_server_id → `agent_moving` then `agent_seated`
- `status_changed` to failed → `agent_error`
- `completed` → `agent_finished`, walk back, `agent_left`

**Modified: `backend/worker/broadcaster.py`**
- Add `office_queue` subscriber type (filtered: run lifecycle + session lifecycle only)
- Purely additive, no changes to existing flow

**Modified: `backend/api/ws.py`**
- Register `ws /ws/office` route

**Desk allocation** (per-client, in-memory):
```python
rooms = {server_id: [None] * server.max_concurrent_tasks}

def assign_desk(room_id, agent_id):
    for i, occupant in enumerate(rooms[room_id]):
        if occupant is None:
            rooms[room_id][i] = agent_id
            return i

def free_desk(room_id, agent_id):
    # find and clear the slot
```

**No database changes required.**

### WebSocket Protocol

**Initial state** (sent on connect):
```json
{
  "type": "office_state",
  "rooms": [
    {"id": "platform", "name": "Platform", "capacity": null},
    {"id": 1, "name": "ws-prod-01", "status": "online", "capacity": 4},
    {"id": 2, "name": "ws-dev-01", "status": "offline", "capacity": 2}
  ],
  "agents": [
    {
      "id": "session-uuid",
      "agent_type": "claude",
      "room_id": 1,
      "desk": 2,
      "status": "active",
      "activity": "coding",
      "project": "my-app",
      "phase": "coding",
      "run_id": 45,
      "duration_seconds": 120,
      "tokens": 15400
    }
  ]
}
```

**Event messages**:
```json
{"type": "agent_spawned",    "agent": {...}, "room_id": "platform"}
{"type": "agent_moving",     "agent_id": "x", "from": "platform", "to": 1}
{"type": "agent_seated",     "agent_id": "x", "room_id": 1, "desk": 3, "activity": "coding"}
{"type": "activity_changed", "agent_id": "x", "activity": "reviewing"}
{"type": "agent_error",      "agent_id": "x", "error": "timeout"}
{"type": "agent_finished",   "agent_id": "x", "from": 1, "to": "platform"}
{"type": "agent_left",       "agent_id": "x"}
{"type": "room_status",      "room_id": 2, "status": "online"}
```

### Sprite Art

**Art style**: Top-down RPG perspective (like early Pokemon/Stardew Valley). 16x16 base sprites at 2-3x render scale.

**Agent sprites** — 6 types: Claude (purple), Codex (green), Aider (blue), Ollama (llama), OpenHands (orange), Generic (gray).

**Animation states**:

| Status | Animation | Frames |
|--------|-----------|--------|
| starting | Standing up | 4 |
| coding | Typing at desk, screen glow | 4 |
| planning | Reading papers | 4 |
| reviewing | Pointing at whiteboard | 4 |
| testing | Looking at screen, sweat | 4 |
| idle/sleeping | Zzz bubbles | 3 |
| walking | Moving sprite | 4 |
| error | Storm cloud overhead | 4 |
| finished | Walking out | 4 |

**Tilesets**: Floor tiles (tinted per room), walls, doors, hallways, desks, chairs, screens, whiteboards, dispatch board, "lights off" overlay.

**Effects**: Zzz bubbles, storm cloud + lightning, sparkle, dust puff, exclamation mark.

**Font**: Press Start 2P (Google Fonts) for room labels and badge counts.

**MVP shortcut**: Start with colored rectangles for rooms and basic 2-frame animations. Replace with proper pixel art iteratively.

### Room Layout Algorithm

1. Platform room fixed on the left side of the canvas
2. Workspace server rooms arranged in a grid to the right
3. Room size scales with `max_concurrent_tasks` (desks inside)
4. Hallways connect all doors
5. Auto-layout recalculates when servers are added/removed
6. Offline servers get a dark semi-transparent overlay

### Interaction Model

**Hover** (via PixiJS hitTest → HTML overlay):
- Agent name and type
- Current phase / status
- Workspace server + project name
- Duration of current activity
- Token count (if running)

**Click** (opens React popover):
- Mini terminal (attaches to `/ws/sessions/{id}/terminal`)
- Kill session button (DELETE `/api/sessions/{id}`)
- "Go to Run Detail" link (`/runs/{run_id}`)

### Nav Icon

- Small animated 24x24 pixel character in the sidebar
- Badge showing count of active agents
- Subtle idle animation (breathing/blinking) when agents are active
- Static when no agents are running

## Success Criteria

- [ ] Character icon appears in nav sidebar with active agent count badge
- [ ] Clicking icon opens full-screen modal with canvas office
- [ ] Platform room and workspace server rooms render correctly
- [ ] Agent sprites appear at desks matching their actual session status
- [ ] Sprites animate according to current activity (coding, planning, reviewing, etc.)
- [ ] When a run starts, platform agent walks to workspace room
- [ ] When a run completes/fails, agent walks back or shows error state
- [ ] Offline servers display "lights off" visual
- [ ] Hover shows tooltip with agent details
- [ ] Click opens control panel with terminal, kill, and navigate actions
- [ ] WebSocket provides real-time updates without polling
- [ ] Modal closes cleanly (ESC, click outside), WebSocket disconnects
- [ ] Canvas resizes with window
