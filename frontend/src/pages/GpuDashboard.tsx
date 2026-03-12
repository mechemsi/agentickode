// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  HardDrive,
  Loader2,
  Monitor,
  Play,
  RefreshCw,
  Server,
  Square,
  Zap,
} from "lucide-react";
import {
  getGpuStatus,
  getOllamaServers,
  preloadModel,
  unloadModel,
} from "../api";
import { useToast } from "../components/shared/Toast";
import type {
  GpuStatusResponse,
  OllamaServer,
  RunningModel,
  RunningModelsResponse,
} from "../types";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / 1024 ** i).toFixed(1)} ${units[i]}`;
}

function timeUntil(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "expiring";
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

function VramBar({ model }: { model: RunningModel }) {
  const total = model.size || 1;
  const vram = model.size_vram || 0;
  const pct = Math.min(100, (vram / total) * 100);
  const cpuPct = 100 - pct;

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>
          GPU: {formatBytes(vram)}
          {cpuPct > 1 && ` / CPU: ${formatBytes(total - vram)}`}
        </span>
        <span>{formatBytes(total)} total</span>
      </div>
      <div className="h-2.5 bg-gray-800 rounded-full overflow-hidden flex">
        {pct > 0 && (
          <div
            className="bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-l-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        )}
        {cpuPct > 1 && (
          <div
            className="bg-gradient-to-r from-amber-600 to-amber-500 transition-all duration-500"
            style={{ width: `${cpuPct}%` }}
          />
        )}
      </div>
      <div className="flex gap-3 mt-1 text-[10px] text-gray-500">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
          GPU {pct.toFixed(0)}%
        </span>
        {cpuPct > 1 && (
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-500 inline-block" />
            CPU {cpuPct.toFixed(0)}%
          </span>
        )}
      </div>
    </div>
  );
}

function ModelCard({
  model,
  serverId,
  onUnload,
  unloading,
}: {
  model: RunningModel;
  serverId: number;
  onUnload: (serverId: number, modelName: string) => void;
  unloading: string | null;
}) {
  const isUnloading = unloading === model.name;

  return (
    <div className="bg-gray-800/50 border border-gray-700/40 rounded-lg p-4 hover:border-gray-600/50 transition-all">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-emerald-400" />
          <span className="font-medium text-white text-sm">{model.name}</span>
        </div>
        <button
          onClick={() => onUnload(serverId, model.name)}
          disabled={isUnloading}
          className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-900/20 transition-colors inline-flex items-center gap-1 disabled:opacity-50"
        >
          {isUnloading ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Square className="w-3 h-3" />
          )}
          {isUnloading ? "Unloading..." : "Unload"}
        </button>
      </div>

      <VramBar model={model} />

      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs text-gray-400">
        {model.details?.parameter_size && (
          <span className="inline-flex items-center gap-1">
            <Cpu className="w-3 h-3" />
            {model.details.parameter_size}
          </span>
        )}
        {model.details?.quantization_level && (
          <span className="inline-flex items-center gap-1">
            <HardDrive className="w-3 h-3" />
            {model.details.quantization_level}
          </span>
        )}
        {model.details?.family && (
          <span className="text-gray-500">{model.details.family}</span>
        )}
        {model.expires_at && (
          <span className="inline-flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {timeUntil(model.expires_at)}
          </span>
        )}
      </div>
    </div>
  );
}

function PreloadControl({
  serverId,
  availableModels,
  onPreload,
  loading,
}: {
  serverId: number;
  availableModels: string[];
  onPreload: (serverId: number, model: string, keepAlive: string | number) => void;
  loading: boolean;
}) {
  const [model, setModel] = useState("");
  const [keepAlive, setKeepAlive] = useState("-1");
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-4 border-t border-gray-700/40 pt-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 transition-colors"
      >
        <Play className="w-3 h-3" />
        Preload Model
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {expanded && (
        <div className="flex gap-2 mt-2 items-end flex-wrap">
          {availableModels.length > 0 ? (
            <select
              className="bg-gray-800/80 border border-gray-700/60 rounded-md px-2 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 flex-1 min-w-[200px]"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="">-- select model --</option>
              {availableModels.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          ) : (
            <input
              className="bg-gray-800/80 border border-gray-700/60 rounded-md px-2 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 flex-1 min-w-[200px]"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="model name (e.g. llama3.2)"
            />
          )}
          <select
            className="bg-gray-800/80 border border-gray-700/60 rounded-md px-2 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            value={keepAlive}
            onChange={(e) => setKeepAlive(e.target.value)}
          >
            <option value="-1">Keep forever</option>
            <option value="5m">5 minutes</option>
            <option value="30m">30 minutes</option>
            <option value="1h">1 hour</option>
            <option value="4h">4 hours</option>
            <option value="24h">24 hours</option>
          </select>
          <button
            onClick={() => {
              if (!model) return;
              const ka = keepAlive === "-1" ? -1 : keepAlive;
              onPreload(serverId, model, ka);
              setModel("");
            }}
            disabled={!model || loading}
            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-md text-sm inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
            {loading ? "Loading..." : "Load"}
          </button>
        </div>
      )}
    </div>
  );
}

function ServerCard({
  server,
  ollamaServer,
  onPreload,
  onUnload,
  preloading,
  unloading,
}: {
  server: RunningModelsResponse;
  ollamaServer: OllamaServer | undefined;
  onPreload: (serverId: number, model: string, keepAlive: string | number) => void;
  onUnload: (serverId: number, modelName: string) => void;
  preloading: number | null;
  unloading: string | null;
}) {
  const isOnline = server.status === "online";
  const availableModels = (ollamaServer?.cached_models || [])
    .map((m) => String(m.name || m.model || ""))
    .filter(Boolean);
  const totalVram = server.models.reduce((sum, m) => sum + (m.size_vram || 0), 0);

  return (
    <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Server className="w-4 h-4 text-gray-400" />
          <span className="font-medium text-white">{server.server_name}</span>
          <span className="text-gray-500 text-sm font-mono">{server.server_url}</span>
        </div>
        <div className="flex items-center gap-2">
          {isOnline && server.models.length > 0 && (
            <span className="text-xs text-gray-400 bg-gray-800/60 px-2 py-0.5 rounded-full">
              {formatBytes(totalVram)} VRAM
            </span>
          )}
          <span
            className={`w-2.5 h-2.5 rounded-full ring-2 ring-gray-900 ${
              isOnline ? "bg-green-500" : "bg-red-500"
            }`}
          />
        </div>
      </div>

      {server.error && (
        <p className="text-red-400 text-xs mb-3">{server.error}</p>
      )}

      {isOnline && server.models.length === 0 && (
        <div className="flex items-center justify-center py-6 text-gray-500">
          <Monitor className="w-5 h-5 mr-2" />
          <span className="text-sm">No models currently loaded</span>
        </div>
      )}

      {server.models.length > 0 && (
        <div className="space-y-2">
          {server.models.map((m) => (
            <ModelCard
              key={m.digest || m.name}
              model={m}
              serverId={server.server_id}
              onUnload={onUnload}
              unloading={unloading}
            />
          ))}
        </div>
      )}

      {isOnline && (
        <PreloadControl
          serverId={server.server_id}
          availableModels={availableModels}
          onPreload={onPreload}
          loading={preloading === server.server_id}
        />
      )}
    </div>
  );
}

export default function GpuDashboard() {
  const [gpuStatus, setGpuStatus] = useState<GpuStatusResponse | null>(null);
  const [ollamaServers, setOllamaServers] = useState<OllamaServer[]>([]);
  const [preloading, setPreloading] = useState<number | null>(null);
  const [unloading, setUnloading] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const toast = useToast();

  const loadStatus = useCallback(async () => {
    try {
      const [status, servers] = await Promise.all([
        getGpuStatus(),
        getOllamaServers(),
      ]);
      setGpuStatus(status);
      setOllamaServers(servers);
    } catch {
      /* polling errors are silent */
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const id = setInterval(loadStatus, 5000);
    return () => clearInterval(id);
  }, [loadStatus]);

  const handlePreload = async (
    serverId: number,
    model: string,
    keepAlive: string | number,
  ) => {
    setPreloading(serverId);
    try {
      const res = await preloadModel(serverId, {
        model,
        keep_alive: keepAlive,
      });
      if (res.success) {
        toast.success(`Loaded ${model}`);
        await loadStatus();
      } else {
        toast.error(res.error || "Failed to preload model");
      }
    } catch {
      toast.error("Failed to preload model");
    } finally {
      setPreloading(null);
    }
  };

  const handleUnload = async (serverId: number, modelName: string) => {
    setUnloading(modelName);
    try {
      const res = await unloadModel(serverId, modelName);
      if (res.success) {
        toast.success(`Unloaded ${modelName}`);
        await loadStatus();
      } else {
        toast.error(res.error || "Failed to unload model");
      }
    } catch {
      toast.error("Failed to unload model");
    } finally {
      setUnloading(null);
    }
  };

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await loadStatus();
    setRefreshing(false);
  };

  const totalModels =
    gpuStatus?.servers.reduce((s, srv) => s + srv.models.length, 0) ?? 0;
  const totalVram =
    gpuStatus?.servers.reduce(
      (s, srv) => s + srv.models.reduce((ms, m) => ms + (m.size_vram || 0), 0),
      0,
    ) ?? 0;
  const onlineCount =
    gpuStatus?.servers.filter((s) => s.status === "online").length ?? 0;

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Activity className="w-5 h-5 text-emerald-400" />
          GPU Dashboard
        </h1>
        <button
          onClick={handleManualRefresh}
          disabled={refreshing}
          className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-3 py-1.5 rounded-lg hover:bg-gray-800/50 transition-colors"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`}
          />
          Refresh
        </button>
      </div>

      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 text-center">
          <p className="text-2xl font-bold text-white">{onlineCount}</p>
          <p className="text-xs text-gray-400 mt-1">Servers Online</p>
        </div>
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 text-center">
          <p className="text-2xl font-bold text-emerald-400">{totalModels}</p>
          <p className="text-xs text-gray-400 mt-1">Models Loaded</p>
        </div>
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 text-center">
          <p className="text-2xl font-bold text-amber-400">
            {formatBytes(totalVram)}
          </p>
          <p className="text-xs text-gray-400 mt-1">VRAM Used</p>
        </div>
      </div>

      {/* Server cards */}
      <div className="space-y-4">
        {gpuStatus?.servers.map((srv) => (
          <ServerCard
            key={srv.server_id}
            server={srv}
            ollamaServer={ollamaServers.find((s) => s.id === srv.server_id)}
            onPreload={handlePreload}
            onUnload={handleUnload}
            preloading={preloading}
            unloading={unloading}
          />
        ))}
        {(!gpuStatus || gpuStatus.servers.length === 0) && (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Server className="w-8 h-8 mb-2 text-gray-600" />
            <p className="text-sm">
              No Ollama servers configured. Add one in{" "}
              <a href="/llm-config" className="text-blue-400 hover:underline">
                Role Configuration
              </a>
              .
            </p>
          </div>
        )}
      </div>
    </>
  );
}