// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Box,
  HardDrive,
  Layers,
  Loader2,
  Network,
  Play,
  RefreshCw,
  ScrollText,
  Square,
  Trash2,
  X,
} from "lucide-react";
import {
  getDockerOverview,
  getContainerLogs,
  startDockerContainer,
  stopDockerContainer,
  restartDockerContainer,
  removeDockerContainer,
  removeDockerImage,
  dockerPrune,
} from "../../api";
import type {
  DockerContainer,
  DockerImage,
  DockerVolume,
  DockerNetwork,
  DockerComposeStack,
  DockerOverview,
} from "../../types";
import { useConfirm } from "../shared/ConfirmDialog";
import { useToast } from "../shared/Toast";

type Tab = "containers" | "images" | "volumes" | "networks" | "stacks" | "cleanup";

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 text-xs rounded transition-colors ${
        active
          ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
          : "text-gray-400 hover:text-white hover:bg-gray-700/50 border border-transparent"
      }`}
    >
      {children}
    </button>
  );
}

function StateIndicator({ state }: { state: string }) {
  const color =
    state === "running" ? "bg-green-400" :
    state === "exited" ? "bg-red-400" :
    state === "paused" ? "bg-yellow-400" :
    "bg-gray-500";
  return <span className={`w-1.5 h-1.5 rounded-full inline-block ${color}`} />;
}

function LogsModal({ title, logs, onClose }: { title: string; logs: string; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs]);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-5 w-full max-w-3xl mx-4 shadow-2xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-white">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white p-1 rounded hover:bg-gray-700/50">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div
          ref={ref}
          className="flex-1 text-xs text-gray-300 bg-gray-950/60 border border-gray-800/50 rounded p-3 font-mono whitespace-pre-wrap break-all overflow-y-auto"
        >
          {logs || "(empty)"}
        </div>
        <div className="flex justify-end mt-3">
          <button onClick={onClose} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function ContainersTab({
  containers,
  serverId,
  onRefresh,
}: {
  containers: DockerContainer[];
  serverId: number;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [logsData, setLogsData] = useState<{ title: string; logs: string } | null>(null);
  const confirm = useConfirm();
  const toast = useToast();

  const act = async (id: string, label: string, fn: () => Promise<unknown>) => {
    setBusy(`${label}-${id}`);
    try {
      await fn();
      toast.success(`${label} ${id.slice(0, 12)} OK`);
      onRefresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `${label} failed`);
    } finally {
      setBusy(null);
    }
  };

  const handleLogs = async (c: DockerContainer) => {
    setBusy(`logs-${c.id}`);
    try {
      const result = await getContainerLogs(serverId, c.id, 200);
      setLogsData({ title: `Logs: ${c.names}`, logs: result.logs });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to fetch logs");
    } finally {
      setBusy(null);
    }
  };

  const handleRemove = async (c: DockerContainer) => {
    const ok = await confirm({
      title: "Remove Container",
      message: `Remove container ${c.names} (${c.id.slice(0, 12)})? This will force-remove it.`,
      confirmLabel: "Remove",
      variant: "danger",
    });
    if (ok) await act(c.id, "Remove", () => removeDockerContainer(serverId, c.id, true));
  };

  if (!containers.length) return <p className="text-xs text-gray-500 py-2">No containers found.</p>;

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800/50">
              <th className="text-left py-1.5 px-2 font-medium">State</th>
              <th className="text-left py-1.5 px-2 font-medium">Name</th>
              <th className="text-left py-1.5 px-2 font-medium">Image</th>
              <th className="text-left py-1.5 px-2 font-medium">Status</th>
              <th className="text-left py-1.5 px-2 font-medium">Ports</th>
              <th className="text-right py-1.5 px-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {containers.map((c) => (
              <tr key={c.id} className="border-b border-gray-800/30 hover:bg-gray-800/20">
                <td className="py-1.5 px-2"><StateIndicator state={c.state} /></td>
                <td className="py-1.5 px-2 text-gray-200 font-mono truncate max-w-[160px]" title={c.names}>{c.names}</td>
                <td className="py-1.5 px-2 text-gray-400 font-mono truncate max-w-[200px]" title={c.image}>{c.image}</td>
                <td className="py-1.5 px-2 text-gray-400">{c.status}</td>
                <td className="py-1.5 px-2 text-gray-500 font-mono truncate max-w-[180px]" title={c.ports}>{c.ports || "-"}</td>
                <td className="py-1.5 px-2 text-right">
                  <div className="flex items-center gap-0.5 justify-end">
                    <button
                      onClick={() => handleLogs(c)}
                      disabled={busy === `logs-${c.id}`}
                      className="p-1 text-gray-400 hover:text-white rounded hover:bg-gray-700/50 disabled:opacity-50"
                      title="View logs"
                    >
                      {busy === `logs-${c.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <ScrollText className="w-3 h-3" />}
                    </button>
                    {c.state !== "running" ? (
                      <button
                        onClick={() => act(c.id, "Start", () => startDockerContainer(serverId, c.id))}
                        disabled={!!busy}
                        className="p-1 text-green-400 hover:text-green-300 rounded hover:bg-green-900/20 disabled:opacity-50"
                        title="Start"
                      >
                        <Play className="w-3 h-3" />
                      </button>
                    ) : (
                      <button
                        onClick={() => act(c.id, "Stop", () => stopDockerContainer(serverId, c.id))}
                        disabled={!!busy}
                        className="p-1 text-yellow-400 hover:text-yellow-300 rounded hover:bg-yellow-900/20 disabled:opacity-50"
                        title="Stop"
                      >
                        <Square className="w-3 h-3" />
                      </button>
                    )}
                    <button
                      onClick={() => act(c.id, "Restart", () => restartDockerContainer(serverId, c.id))}
                      disabled={!!busy}
                      className="p-1 text-blue-400 hover:text-blue-300 rounded hover:bg-blue-900/20 disabled:opacity-50"
                      title="Restart"
                    >
                      <RefreshCw className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => handleRemove(c)}
                      disabled={!!busy}
                      className="p-1 text-red-400 hover:text-red-300 rounded hover:bg-red-900/20 disabled:opacity-50"
                      title="Remove"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {logsData && <LogsModal title={logsData.title} logs={logsData.logs} onClose={() => setLogsData(null)} />}
    </>
  );
}

function ImagesTab({
  images,
  serverId,
  onRefresh,
}: {
  images: DockerImage[];
  serverId: number;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();
  const toast = useToast();

  const handleRemove = async (img: DockerImage) => {
    const label = `${img.repository}:${img.tag}`;
    const ok = await confirm({
      title: "Remove Image",
      message: `Remove image ${label}?`,
      confirmLabel: "Remove",
      variant: "danger",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await removeDockerImage(serverId, img.id, true);
      toast.success(`Removed ${label}`);
      onRefresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to remove image");
    } finally {
      setBusy(false);
    }
  };

  if (!images.length) return <p className="text-xs text-gray-500 py-2">No images found.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800/50">
            <th className="text-left py-1.5 px-2 font-medium">Repository</th>
            <th className="text-left py-1.5 px-2 font-medium">Tag</th>
            <th className="text-left py-1.5 px-2 font-medium">Size</th>
            <th className="text-left py-1.5 px-2 font-medium">ID</th>
            <th className="text-right py-1.5 px-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {images.map((img) => (
            <tr key={img.id} className="border-b border-gray-800/30 hover:bg-gray-800/20">
              <td className="py-1.5 px-2 text-gray-200 font-mono truncate max-w-[200px]">{img.repository}</td>
              <td className="py-1.5 px-2 text-gray-400">{img.tag}</td>
              <td className="py-1.5 px-2 text-gray-400">{img.size}</td>
              <td className="py-1.5 px-2 text-gray-500 font-mono">{img.id.slice(0, 12)}</td>
              <td className="py-1.5 px-2 text-right">
                <button
                  onClick={() => handleRemove(img)}
                  disabled={busy}
                  className="p-1 text-red-400 hover:text-red-300 rounded hover:bg-red-900/20 disabled:opacity-50"
                  title="Remove image"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VolumesTab({ volumes }: { volumes: DockerVolume[] }) {
  if (!volumes.length) return <p className="text-xs text-gray-500 py-2">No volumes found.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800/50">
            <th className="text-left py-1.5 px-2 font-medium">Name</th>
            <th className="text-left py-1.5 px-2 font-medium">Driver</th>
            <th className="text-left py-1.5 px-2 font-medium">Mountpoint</th>
          </tr>
        </thead>
        <tbody>
          {volumes.map((v) => (
            <tr key={v.name} className="border-b border-gray-800/30 hover:bg-gray-800/20">
              <td className="py-1.5 px-2 text-gray-200 font-mono">{v.name}</td>
              <td className="py-1.5 px-2 text-gray-400">{v.driver}</td>
              <td className="py-1.5 px-2 text-gray-500 font-mono truncate max-w-[300px]" title={v.mountpoint || ""}>{v.mountpoint || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NetworksTab({ networks }: { networks: DockerNetwork[] }) {
  if (!networks.length) return <p className="text-xs text-gray-500 py-2">No networks found.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800/50">
            <th className="text-left py-1.5 px-2 font-medium">Name</th>
            <th className="text-left py-1.5 px-2 font-medium">Driver</th>
            <th className="text-left py-1.5 px-2 font-medium">Scope</th>
            <th className="text-left py-1.5 px-2 font-medium">ID</th>
          </tr>
        </thead>
        <tbody>
          {networks.map((n) => (
            <tr key={n.id} className="border-b border-gray-800/30 hover:bg-gray-800/20">
              <td className="py-1.5 px-2 text-gray-200">{n.name}</td>
              <td className="py-1.5 px-2 text-gray-400">{n.driver}</td>
              <td className="py-1.5 px-2 text-gray-400">{n.scope}</td>
              <td className="py-1.5 px-2 text-gray-500 font-mono">{n.id.slice(0, 12)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StacksTab({ stacks }: { stacks: DockerComposeStack[] }) {
  if (!stacks.length) return <p className="text-xs text-gray-500 py-2">No compose stacks found.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800/50">
            <th className="text-left py-1.5 px-2 font-medium">Name</th>
            <th className="text-left py-1.5 px-2 font-medium">Status</th>
            <th className="text-left py-1.5 px-2 font-medium">Config Files</th>
          </tr>
        </thead>
        <tbody>
          {stacks.map((s) => (
            <tr key={s.name} className="border-b border-gray-800/30 hover:bg-gray-800/20">
              <td className="py-1.5 px-2 text-gray-200 font-mono">{s.name}</td>
              <td className="py-1.5 px-2 text-gray-400">{s.status}</td>
              <td className="py-1.5 px-2 text-gray-500 font-mono truncate max-w-[300px]" title={s.config_files || ""}>{s.config_files || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CleanupTab({ serverId, diskUsage, onRefresh }: { serverId: number; diskUsage: string; onRefresh: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [pruneOutput, setPruneOutput] = useState<string | null>(null);
  const confirm = useConfirm();
  const toast = useToast();

  const handlePrune = async (target: string, label: string, all = false, includeVolumes = false) => {
    const msg = target === "system"
      ? `Run system prune${all ? " (all)" : ""}${includeVolumes ? " including volumes" : ""}? This removes unused Docker resources.`
      : `Prune unused ${label}?`;
    const ok = await confirm({
      title: `Prune ${label}`,
      message: msg,
      confirmLabel: "Prune",
      variant: "danger",
    });
    if (!ok) return;
    setBusy(target);
    try {
      const result = await dockerPrune(serverId, target, all, includeVolumes);
      setPruneOutput(result.output);
      toast.success(`${label} pruned`);
      onRefresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Prune failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-medium text-gray-300 mb-2">Disk Usage</h4>
        <pre className="text-xs text-gray-400 bg-gray-950/60 border border-gray-800/50 rounded p-3 font-mono whitespace-pre overflow-x-auto">
          {diskUsage || "Loading..."}
        </pre>
      </div>
      <div>
        <h4 className="text-xs font-medium text-gray-300 mb-2">Prune Resources</h4>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => handlePrune("containers", "Containers")}
            disabled={!!busy}
            className="px-2.5 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded transition-colors inline-flex items-center gap-1.5"
          >
            {busy === "containers" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
            Prune Containers
          </button>
          <button
            onClick={() => handlePrune("images", "Images")}
            disabled={!!busy}
            className="px-2.5 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded transition-colors inline-flex items-center gap-1.5"
          >
            {busy === "images" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
            Prune Images
          </button>
          <button
            onClick={() => handlePrune("images", "All Images", true)}
            disabled={!!busy}
            className="px-2.5 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded transition-colors inline-flex items-center gap-1.5"
          >
            {busy === "images" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
            Prune All Images
          </button>
          <button
            onClick={() => handlePrune("volumes", "Volumes")}
            disabled={!!busy}
            className="px-2.5 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded transition-colors inline-flex items-center gap-1.5"
          >
            {busy === "volumes" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
            Prune Volumes
          </button>
          <button
            onClick={() => handlePrune("networks", "Networks")}
            disabled={!!busy}
            className="px-2.5 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded transition-colors inline-flex items-center gap-1.5"
          >
            {busy === "networks" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
            Prune Networks
          </button>
          <button
            onClick={() => handlePrune("system", "System", true, true)}
            disabled={!!busy}
            className="px-2.5 py-1.5 text-xs bg-red-900/30 hover:bg-red-900/50 border border-red-800/40 disabled:opacity-50 text-red-300 rounded transition-colors inline-flex items-center gap-1.5"
          >
            {busy === "system" ? <Loader2 className="w-3 h-3 animate-spin" /> : <AlertTriangle className="w-3 h-3" />}
            System Prune (all + volumes)
          </button>
        </div>
      </div>
      {pruneOutput && (
        <div>
          <h4 className="text-xs font-medium text-gray-300 mb-1">Prune Output</h4>
          <pre className="text-xs text-gray-400 bg-gray-950/60 border border-gray-800/50 rounded p-3 font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
            {pruneOutput}
          </pre>
        </div>
      )}
    </div>
  );
}

export default function DockerPanel({ serverId }: { serverId: number }) {
  const [data, setData] = useState<DockerOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("containers");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getDockerOverview(serverId);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Docker info");
    } finally {
      setLoading(false);
    }
  }, [serverId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-xs py-2">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading Docker info...
      </div>
    );
  }

  if (error && !data) {
    return <p className="text-red-400 text-xs py-2">{error}</p>;
  }

  if (!data) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium text-gray-300 inline-flex items-center gap-1.5">
            <Box className="w-3.5 h-3.5" />
            Docker
          </span>
          <TabButton active={tab === "containers"} onClick={() => setTab("containers")}>
            <span className="inline-flex items-center gap-1"><Box className="w-3 h-3" /> Containers ({data.containers.length})</span>
          </TabButton>
          <TabButton active={tab === "images"} onClick={() => setTab("images")}>
            <span className="inline-flex items-center gap-1"><Layers className="w-3 h-3" /> Images ({data.images.length})</span>
          </TabButton>
          <TabButton active={tab === "volumes"} onClick={() => setTab("volumes")}>
            <span className="inline-flex items-center gap-1"><HardDrive className="w-3 h-3" /> Volumes ({data.volumes.length})</span>
          </TabButton>
          <TabButton active={tab === "networks"} onClick={() => setTab("networks")}>
            <span className="inline-flex items-center gap-1"><Network className="w-3 h-3" /> Networks ({data.networks.length})</span>
          </TabButton>
          <TabButton active={tab === "stacks"} onClick={() => setTab("stacks")}>
            Stacks ({data.stacks.length})
          </TabButton>
          <TabButton active={tab === "cleanup"} onClick={() => setTab("cleanup")}>
            <span className="inline-flex items-center gap-1"><Trash2 className="w-3 h-3" /> Cleanup</span>
          </TabButton>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-gray-500 hover:text-gray-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && <p className="text-red-400 text-xs">{error}</p>}

      {tab === "containers" && <ContainersTab containers={data.containers} serverId={serverId} onRefresh={load} />}
      {tab === "images" && <ImagesTab images={data.images} serverId={serverId} onRefresh={load} />}
      {tab === "volumes" && <VolumesTab volumes={data.volumes} />}
      {tab === "networks" && <NetworksTab networks={data.networks} />}
      {tab === "stacks" && <StacksTab stacks={data.stacks} />}
      {tab === "cleanup" && <CleanupTab serverId={serverId} diskUsage={data.disk_usage} onRefresh={load} />}
    </div>
  );
}
