// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useRef, useState, useCallback } from 'react';
import type { OfficeRoom, OfficeAgent, OfficeEvent } from '../../hooks/useOfficeSocket';
import OfficeTooltip from './OfficeTooltip';
import OfficeControlPanel from './OfficeControlPanel';

// ============================================================
// Pokemon-style 8-bit Office — Pure Canvas2D (Firefox-safe)
// ============================================================

const BASE_TILE = 16;

// Pokemon Gen 3/4 indoor palette
const PAL = {
  floorA:    '#E8D4A0',
  floorB:    '#D4C08C',
  wallTop:   '#8B7355',
  wallFront: '#6B5740',
  wallDark:  '#4A3C2A',
  wallLight: '#A08C6C',
  desk:      '#7B5B3A',
  deskTop:   '#9B7B5A',
  deskLight: '#B89B6A',
  screen:    '#1A1A2E',
  chair:     '#4A3C6A',
  hallway:   '#C8B488',
  hallwayB:  '#BDA878',
  doorFrame: '#6B5740',
  labelBg:   '#4A3C2A',
  shadow:    'rgba(0,0,0,0.15)',
};

const AGENT_COLORS: Record<string, string> = {
  claude: '#9F7AEA', codex: '#48BB78', aider: '#4299E1',
  ollama: '#ED8936', openhands: '#FC8181', generic: '#A0AEC0',
};

const ACTIVITY_SCREEN: Record<string, string> = {
  coding: '#48BB78', planning: '#4299E1', reviewing: '#ECC94B',
  testing: '#ED8936', idle: '#2D3748', starting: '#4299E1', error: '#FC5185',
};

// ============================================================
// Layout
// ============================================================

interface DeskSlot {
  tileX: number;
  tileY: number;
  occupied: string | null;
  // screen coords (computed during draw)
  screenX: number;
  screenY: number;
}

interface RoomRect {
  id: string | number;
  name: string;
  status: string;
  x: number;
  y: number;
  w: number;
  h: number;
  desks: DeskSlot[];
  capacity: number;
}

function layoutRooms(rooms: Map<string | number, OfficeRoom>): { worldW: number; worldH: number; rects: RoomRect[] } {
  const roomArr = Array.from(rooms.values());
  const platformRoom = roomArr.find(r => r.id === 'platform');
  const serverRooms = roomArr.filter(r => r.id !== 'platform');
  const rects: RoomRect[] = [];
  const GAP = 3;
  const WALL = 2;

  function makeRoom(room: OfficeRoom, cap: number, x: number, y: number): RoomRect {
    const cols = Math.min(cap, 2);
    const rows = Math.ceil(cap / cols);
    const innerW = Math.max(cols * 3 + 1, 5);
    const innerH = rows * 2 + 2;
    const desks: DeskSlot[] = [];
    for (let i = 0; i < cap; i++) {
      const c = i % cols;
      const r = Math.floor(i / cols);
      desks.push({ tileX: 1 + c * 3, tileY: 2 + r * 2, occupied: null, screenX: 0, screenY: 0 });
    }
    return { id: room.id, name: room.name, status: room.status || 'unknown', x, y, w: innerW, h: innerH, desks, capacity: cap };
  }

  // Platform room on the left
  if (platformRoom) {
    rects.push(makeRoom(platformRoom, 6, 1, 1));
  }

  // Server rooms in a 2-column grid to the right
  const startX = rects.length > 0 ? rects[0].x + rects[0].w + WALL + GAP : 1;
  const colWidth = 12; // tiles per column
  const rowHeight = 8; // tiles per row
  const gridCols = Math.min(2, serverRooms.length);

  for (let i = 0; i < serverRooms.length; i++) {
    const room = serverRooms[i];
    const col = i % gridCols;
    const row = Math.floor(i / gridCols);
    const cap = room.capacity || 4;
    const x = startX + col * (colWidth + GAP);
    const y = 1 + row * (rowHeight + GAP);
    rects.push(makeRoom(room, cap, x, y));
  }

  let maxX = 0, maxY = 0;
  for (const r of rects) {
    maxX = Math.max(maxX, r.x + r.w + 2);
    maxY = Math.max(maxY, r.y + r.h + 2);
  }

  return { worldW: maxX + 1, worldH: maxY + 1, rects };
}

// ============================================================
// Drawing
// ============================================================

function drawCheckerFloor(ctx: CanvasRenderingContext2D, T: number, x: number, y: number, w: number, h: number, offline: boolean) {
  for (let ty = 0; ty < h; ty++) {
    for (let tx = 0; tx < w; tx++) {
      const px = (x + tx) * T;
      const py = (y + ty) * T;
      ctx.fillStyle = offline
        ? ((tx + ty) % 2 === 0 ? '#3A3A4A' : '#32323F')
        : ((tx + ty) % 2 === 0 ? PAL.floorA : PAL.floorB);
      ctx.fillRect(px, py, T, T);
    }
  }
}

function drawWalls(ctx: CanvasRenderingContext2D, T: number, x: number, y: number, w: number, h: number, offline: boolean) {
  const px = x * T, py = y * T, pw = w * T, ph = h * T;
  const wallH = T * 1.5;

  ctx.fillStyle = offline ? '#2A2A2A' : PAL.wallTop;
  ctx.fillRect(px - T, py - wallH, pw + T * 2, wallH);
  ctx.fillStyle = offline ? '#222222' : PAL.wallFront;
  ctx.fillRect(px - T, py - 4, pw + T * 2, 4);
  ctx.fillRect(px - T, py, T, ph);
  ctx.fillRect(px + pw, py, T, ph);
  ctx.fillRect(px - T, py + ph, pw + T * 2, T * 0.5);

  ctx.fillStyle = offline ? '#3A3A3A' : PAL.wallLight;
  ctx.fillRect(px - T, py - wallH, pw + T * 2, 3);
  ctx.fillStyle = offline ? '#1A1A1A' : PAL.wallDark;
  ctx.fillRect(px - T, py - 1, pw + T * 2, 2);

  // Door
  const doorW = T * 2;
  const doorX = px + (pw - doorW) / 2;
  const doorY = py + ph;
  ctx.fillStyle = offline ? '#32323F' : PAL.floorA;
  ctx.fillRect(doorX, doorY, doorW, T * 0.5);
  ctx.fillStyle = offline ? '#3A3A3A' : PAL.doorFrame;
  ctx.fillRect(doorX - 3, doorY, 3, T * 0.5);
  ctx.fillRect(doorX + doorW, doorY, 3, T * 0.5);
}

function drawDesk(ctx: CanvasRenderingContext2D, T: number, px: number, py: number, active: boolean, offline: boolean) {
  const dw = T * 2, dh = T * 0.7, dy = py + T * 0.3;

  ctx.fillStyle = PAL.shadow;
  ctx.fillRect(px + 3, dy + 3, dw, dh);
  ctx.fillStyle = offline ? '#3A3A3A' : PAL.deskTop;
  ctx.fillRect(px, dy, dw, dh);
  ctx.fillStyle = offline ? '#2A2A2A' : PAL.desk;
  ctx.fillRect(px, dy + dh, dw, T * 0.3);
  ctx.fillStyle = offline ? '#4A4A4A' : PAL.deskLight;
  ctx.fillRect(px + 2, dy + 2, dw - 4, 2);

  // Monitor
  const monW = T * 0.7, monH = T * 0.5;
  const monX = px + (dw - monW) / 2, monY = dy - monH + 2;
  ctx.fillStyle = '#2D2D2D';
  ctx.fillRect(monX, monY, monW, monH);
  ctx.fillStyle = active && !offline ? ACTIVITY_SCREEN.coding : PAL.screen;
  ctx.fillRect(monX + 2, monY + 2, monW - 4, monH - 4);
  if (active && !offline) {
    ctx.fillStyle = 'rgba(72, 187, 120, 0.15)';
    ctx.fillRect(monX - 4, monY - 4, monW + 8, monH + 8);
  }
  ctx.fillStyle = '#2D2D2D';
  ctx.fillRect(monX + monW / 2 - 2, monY + monH, 4, 3);

  // Chair
  const chairY = py + T * 1.2, chairX = px + dw / 2 - T * 0.3;
  ctx.fillStyle = offline ? '#2A2A3A' : PAL.chair;
  ctx.fillRect(chairX, chairY, T * 0.6, T * 0.5);
  ctx.fillRect(chairX + 2, chairY - T * 0.2, T * 0.6 - 4, T * 0.25);
}

function drawAgent(ctx: CanvasRenderingContext2D, T: number, px: number, py: number, agent: OfficeAgent, frame: number) {
  const color = AGENT_COLORS[agent.agent_type] || AGENT_COLORS.generic;
  const actColor = ACTIVITY_SCREEN[agent.activity] || ACTIVITY_SCREEN.idle;
  const bob = agent.activity === 'idle' ? 0 : Math.sin(frame * 0.08) * 2;

  // Shadow
  ctx.fillStyle = 'rgba(0,0,0,0.2)';
  ctx.beginPath();
  ctx.ellipse(px, py + T * 0.45, T * 0.35, T * 0.1, 0, 0, Math.PI * 2);
  ctx.fill();

  // Body
  ctx.fillStyle = color;
  ctx.fillRect(px - T * 0.25, py - T * 0.1 + bob, T * 0.5, T * 0.4);
  // Head
  ctx.fillRect(px - T * 0.2, py - T * 0.4 + bob, T * 0.4, T * 0.35);
  // Eyes
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(px - T * 0.1, py - T * 0.25 + bob, T * 0.07, T * 0.07);
  ctx.fillRect(px + T * 0.05, py - T * 0.25 + bob, T * 0.07, T * 0.07);

  // Activity dot
  ctx.fillStyle = actColor;
  ctx.beginPath();
  ctx.arc(px, py - T * 0.5 + bob, T * 0.08, 0, Math.PI * 2);
  ctx.fill();

  // Zzz for idle
  if (agent.activity === 'idle' || agent.activity === 'starting') {
    const zOff = Math.sin(frame * 0.05) * 3;
    ctx.fillStyle = '#A0AEC0';
    ctx.font = `${Math.round(T * 0.22)}px "Press Start 2P", monospace`;
    ctx.fillText('z', px + T * 0.2, py - T * 0.5 + zOff);
    ctx.font = `${Math.round(T * 0.16)}px "Press Start 2P", monospace`;
    ctx.fillText('z', px + T * 0.35, py - T * 0.65 + zOff - 3);
  }

  // Error cloud
  if (agent.activity === 'error') {
    ctx.fillStyle = '#4A5568';
    ctx.beginPath();
    ctx.arc(px - T * 0.15, py - T * 0.7, T * 0.15, 0, Math.PI * 2);
    ctx.arc(px + T * 0.1, py - T * 0.7, T * 0.18, 0, Math.PI * 2);
    ctx.arc(px, py - T * 0.8, T * 0.15, 0, Math.PI * 2);
    ctx.fill();
    if (frame % 30 < 15) {
      ctx.fillStyle = '#ECC94B';
      ctx.fillRect(px - 2, py - T * 0.6, 4, T * 0.15);
    }
  }

  // Label
  ctx.fillStyle = '#FFFFFF';
  ctx.font = `${Math.round(T * 0.18)}px "Press Start 2P", monospace`;
  ctx.textAlign = 'center';
  ctx.fillText(agent.agent_type.slice(0, 6), px, py + T * 0.6);
  ctx.textAlign = 'left';
}

function drawRoomLabel(ctx: CanvasRenderingContext2D, T: number, x: number, y: number, w: number, name: string, offline: boolean) {
  const px = x * T;
  const py = y * T - T * 1.5 + T * 0.3;
  const fontSize = Math.round(T * 0.22);
  ctx.font = `${fontSize}px "Press Start 2P", monospace`;
  const measured = ctx.measureText(name);
  const labelW = measured.width + T * 0.5;

  ctx.fillStyle = offline ? '#2A2A2A' : PAL.labelBg;
  ctx.fillRect(px + (w * T - labelW) / 2, py, labelW, T * 0.5);
  ctx.fillStyle = offline ? '#666666' : '#FFFFFF';
  ctx.textAlign = 'center';
  ctx.fillText(name, px + w * T / 2, py + T * 0.37);
  ctx.textAlign = 'left';

  // Status dot
  ctx.fillStyle = offline ? '#FC5185' : '#48BB78';
  ctx.beginPath();
  ctx.arc(px + (w * T + labelW) / 2 - T * 0.12, py + T * 0.25, T * 0.06, 0, Math.PI * 2);
  ctx.fill();
}

function drawHallwayFloor(ctx: CanvasRenderingContext2D, T: number, worldW: number, worldH: number) {
  for (let ty = 0; ty < worldH; ty++) {
    for (let tx = 0; tx < worldW; tx++) {
      ctx.fillStyle = (tx + ty) % 2 === 0 ? PAL.hallway : PAL.hallwayB;
      ctx.fillRect(tx * T, ty * T, T, T);
    }
  }
}

// ============================================================
// Component
// ============================================================

interface Props {
  rooms: Map<string | number, OfficeRoom>;
  agents: Map<string, OfficeAgent>;
  onEvent: (cb: (event: OfficeEvent) => void) => () => void;
}

export default function OfficeCanvas({ rooms, agents, onEvent }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef(0);
  const animRef = useRef<number>(0);
  const layoutRef = useRef<{ worldW: number; worldH: number; rects: RoomRect[] }>({ worldW: 0, worldH: 0, rects: [] });
  const scaleRef = useRef(3);
  const offsetRef = useRef({ x: 0, y: 0 });

  // Tooltip / control panel state
  const [hoveredAgent, setHoveredAgent] = useState<{ agent: OfficeAgent; x: number; y: number } | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<{ agent: OfficeAgent; x: number; y: number } | null>(null);

  void onEvent;

  // Resize canvas
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const resize = () => {
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Recalculate layout
  useEffect(() => {
    layoutRef.current = layoutRooms(rooms);

    // Auto-fit: calculate scale to fit world in viewport
    const canvas = canvasRef.current;
    if (!canvas) return;
    const { worldW, worldH } = layoutRef.current;
    if (worldW === 0 || worldH === 0) return;

    const scaleX = canvas.width / (worldW * BASE_TILE);
    const scaleY = canvas.height / (worldH * BASE_TILE);
    const scale = Math.min(scaleX, scaleY, 4) * 0.92; // 92% to add margin
    scaleRef.current = scale;

    const totalW = worldW * BASE_TILE * scale;
    const totalH = worldH * BASE_TILE * scale;
    offsetRef.current = {
      x: Math.max(0, (canvas.width - totalW) / 2),
      y: Math.max(0, (canvas.height - totalH) / 2),
    };
  }, [rooms]);

  // Find agent at screen position
  const findAgentAt = useCallback((screenX: number, screenY: number): { agent: OfficeAgent; x: number; y: number } | null => {
    const scale = scaleRef.current;
    const T = BASE_TILE * scale;
    const offset = offsetRef.current;
    const hitRadius = T * 0.6;

    for (const [, room] of layoutRef.current.rects.entries()) {
      for (const desk of room.desks) {
        if (!desk.occupied) continue;
        const agent = agents.get(desk.occupied);
        if (!agent) continue;

        // Agent screen position (center)
        const agentX = offset.x + (room.x + desk.tileX) * T + T;
        const agentY = offset.y + (room.y + desk.tileY) * T + T * 1.2;

        const dx = screenX - agentX;
        const dy = screenY - agentY;
        if (dx * dx + dy * dy < hitRadius * hitRadius) {
          return { agent, x: agentX, y: agentY };
        }
      }
    }
    return null;
  }, [agents]);

  // Mouse handlers
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (selectedAgent) return; // don't change tooltip while control panel is open
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const hit = findAgentAt(x, y);
    setHoveredAgent(hit);
    if (canvasRef.current) {
      canvasRef.current.style.cursor = hit ? 'pointer' : 'default';
    }
  }, [findAgentAt, selectedAgent]);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const hit = findAgentAt(x, y);
    if (hit) {
      setSelectedAgent(hit);
      setHoveredAgent(null);
    } else {
      setSelectedAgent(null);
    }
  }, [findAgentAt]);

  // Animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      frameRef.current++;
      const { worldW, worldH, rects } = layoutRef.current;
      if (rects.length === 0) {
        animRef.current = requestAnimationFrame(draw);
        return;
      }

      const cw = canvas.width;
      const ch = canvas.height;
      const scale = scaleRef.current;
      const T = BASE_TILE * scale;
      const offset = offsetRef.current;

      ctx.clearRect(0, 0, cw, ch);
      ctx.fillStyle = '#0D1117';
      ctx.fillRect(0, 0, cw, ch);

      ctx.save();
      ctx.translate(offset.x, offset.y);

      drawHallwayFloor(ctx, T, worldW, worldH);

      // Clear desk occupancy
      for (const room of rects) {
        for (const desk of room.desks) {
          desk.occupied = null;
        }
      }
      // Assign agents to desks
      for (const [id, agent] of agents) {
        const room = rects.find(r => r.id === agent.room_id);
        if (!room) continue;
        let desk = room.desks.find(d => d.occupied === id);
        if (!desk) {
          desk = room.desks.find(d => d.occupied === null);
          if (desk) desk.occupied = id;
        }
      }

      // Draw rooms
      for (const room of rects) {
        const offline = room.status === 'offline' || room.status === 'unknown';
        drawCheckerFloor(ctx, T, room.x, room.y, room.w, room.h, offline);
        drawWalls(ctx, T, room.x, room.y, room.w, room.h, offline);
        drawRoomLabel(ctx, T, room.x, room.y, room.w, room.name, offline);

        for (const desk of room.desks) {
          const deskPx = (room.x + desk.tileX) * T;
          const deskPy = (room.y + desk.tileY) * T;
          drawDesk(ctx, T, deskPx, deskPy, desk.occupied !== null, offline);

          // Store screen coords for hit testing
          desk.screenX = offset.x + (room.x + desk.tileX) * T + T;
          desk.screenY = offset.y + (room.y + desk.tileY) * T + T * 1.2;
        }

        if (offline) {
          ctx.fillStyle = 'rgba(0,0,0,0.3)';
          ctx.fillRect(room.x * T, room.y * T, room.w * T, room.h * T);
          ctx.fillStyle = '#FC5185';
          ctx.font = `${Math.round(T * 0.25)}px "Press Start 2P", monospace`;
          ctx.textAlign = 'center';
          ctx.fillText('OFFLINE', (room.x + room.w / 2) * T, (room.y + room.h / 2) * T);
          ctx.textAlign = 'left';
        }
      }

      // Draw agents
      for (const room of rects) {
        for (const desk of room.desks) {
          if (!desk.occupied) continue;
          const agent = agents.get(desk.occupied);
          if (!agent) continue;
          const agentPx = (room.x + desk.tileX) * T + T;
          const agentPy = (room.y + desk.tileY) * T + T * 1.2;
          drawAgent(ctx, T, agentPx, agentPy, agent, frameRef.current);
        }
      }

      ctx.restore();

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [rooms, agents]);

  return (
    <div ref={containerRef} className="w-full h-full relative">
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onClick={handleClick}
        onMouseLeave={() => { if (!selectedAgent) setHoveredAgent(null); }}
        style={{ imageRendering: 'pixelated', width: '100%', height: '100%' }}
      />
      {hoveredAgent && !selectedAgent && (
        <OfficeTooltip agent={hoveredAgent.agent} x={hoveredAgent.x} y={hoveredAgent.y} />
      )}
      {selectedAgent && (
        <OfficeControlPanel
          agent={selectedAgent.agent}
          x={selectedAgent.x}
          y={selectedAgent.y}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
}
