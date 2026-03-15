// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useState } from "react";
import { Check, Globe, Loader2, Plus, Pencil, Server, Star, Trash2, Wifi } from "lucide-react";
import {
  createGitConnection,
  deleteGitConnection,
  getGitConnections,
  testGitConnection,
  updateGitConnection,
} from "../../api";
import type { GitConnection, GitConnectionCreate } from "../../types";
import { useConfirm } from "../shared/ConfirmDialog";
import { useToast } from "../shared/Toast";
import GitConnectionForm from "./GitConnectionForm";

const PROVIDER_COLORS: Record<string, string> = {
  github: "bg-gray-600/30 border-gray-600/50 text-gray-300",
  gitlab: "bg-orange-600/15 border-orange-700/40 text-orange-400",
  bitbucket: "bg-blue-600/15 border-blue-700/40 text-blue-400",
  gitea: "bg-green-600/15 border-green-700/40 text-green-400",
};

const PROVIDER_LABELS: Record<string, string> = {
  github: "GitHub",
  gitlab: "GitLab",
  bitbucket: "Bitbucket",
  gitea: "Gitea",
};

function ProviderBadge({ provider }: { provider: string }) {
  const colors = PROVIDER_COLORS[provider] || PROVIDER_COLORS.github;
  const label = PROVIDER_LABELS[provider] || provider;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs border ${colors}`}>
      {label}
    </span>
  );
}

function ScopeBadge({ scope }: { scope: string }) {
  if (scope === "global") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-purple-600/15 border border-purple-700/40 text-purple-400">
        <Globe className="w-3 h-3" />
        Global
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-gray-600/20 border border-gray-700/40 text-gray-400">
      <Server className="w-3 h-3" />
      Server
    </span>
  );
}

export default function GitConnectionsPanel({ serverId }: { serverId: number }) {
  const [connections, setConnections] = useState<GitConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, { success: boolean; username?: string | null; error?: string | null }>>({});
  const toast = useToast();
  const confirm = useConfirm();

  const load = useCallback(async () => {
    try {
      const data = await getGitConnections({ workspace_server_id: serverId });
      setConnections(data);
    } catch {
      setConnections([]);
    } finally {
      setLoading(false);
    }
  }, [serverId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (data: GitConnectionCreate | Partial<GitConnectionCreate>) => {
    await createGitConnection(data as GitConnectionCreate);
    toast.success("Git connection created");
    setAdding(false);
    load();
  };

  const handleUpdate = async (id: number, data: Partial<GitConnectionCreate>) => {
    await updateGitConnection(id, data);
    toast.success("Git connection updated");
    setEditingId(null);
    load();
  };

  const handleDelete = async (id: number) => {
    const ok = await confirm({
      title: "Delete Connection",
      message: "Delete this git connection? This will remove the stored token.",
      confirmLabel: "Delete",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await deleteGitConnection(id);
      toast.success("Connection deleted");
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  const handleTest = async (id: number) => {
    setTestingId(id);
    setTestResults((prev) => ({ ...prev, [id]: undefined as unknown as typeof prev[number] }));
    try {
      const result = await testGitConnection(id);
      setTestResults((prev) => ({
        ...prev,
        [id]: { success: result.success, username: result.username, error: result.error },
      }));
      if (result.success) {
        toast.success(`Connected as ${result.username}`);
      } else {
        toast.error(`Test failed: ${result.error}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Test failed";
      setTestResults((prev) => ({ ...prev, [id]: { success: false, error: msg } }));
      toast.error(msg);
    } finally {
      setTestingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-xs py-2">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading git connections...
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {connections.length === 0 && !adding && (
        <p className="text-xs text-gray-500">No git token connections configured.</p>
      )}

      {connections.map((conn) => {
        if (editingId === conn.id) {
          return (
            <div key={conn.id} className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3">
              <GitConnectionForm
                serverId={serverId}
                existing={conn}
                onSave={(data) => handleUpdate(conn.id, data as Partial<GitConnectionCreate>)}
                onCancel={() => setEditingId(null)}
              />
            </div>
          );
        }

        const result = testResults[conn.id];

        return (
          <div
            key={conn.id}
            className="flex items-center justify-between gap-3 bg-gray-800/30 border border-gray-700/40 rounded-lg px-3 py-2"
          >
            <div className="flex items-center gap-2 min-w-0">
              <ProviderBadge provider={conn.provider} />
              <span className="text-sm text-white truncate">{conn.name}</span>
              <ScopeBadge scope={conn.scope} />
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-green-500/10 border border-green-800/40 text-green-400">
                <Check className="w-3 h-3" />
                Configured
              </span>
              {conn.is_default && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-yellow-500/10 border border-yellow-700/40 text-yellow-400">
                  <Star className="w-3 h-3" />
                  Default
                </span>
              )}
              {result && (
                <span className={`text-xs ${result.success ? "text-green-400" : "text-red-400"}`}>
                  {result.success ? `OK (${result.username})` : result.error}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => handleTest(conn.id)}
                disabled={testingId === conn.id}
                className="text-xs text-gray-400 hover:text-white disabled:opacity-50 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                title="Test connection"
              >
                {testingId === conn.id ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Wifi className="w-3 h-3" />
                )}
                Test
              </button>
              <button
                onClick={() => setEditingId(conn.id)}
                className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                title="Edit connection"
              >
                <Pencil className="w-3 h-3" />
              </button>
              <button
                onClick={() => handleDelete(conn.id)}
                className="text-xs text-red-400 hover:text-red-300 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-red-900/20 transition-colors"
                title="Delete connection"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          </div>
        );
      })}

      {adding && (
        <div className="bg-gray-800/40 border border-gray-700/50 rounded-lg p-3">
          <GitConnectionForm
            serverId={serverId}
            onSave={handleCreate}
            onCancel={() => setAdding(false)}
          />
        </div>
      )}

      {!adding && (
        <button
          onClick={() => { setAdding(true); setEditingId(null); }}
          className="text-xs text-blue-400 hover:text-blue-300 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-blue-900/20 transition-colors"
        >
          <Plus className="w-3 h-3" />
          Add Connection
        </button>
      )}
    </div>
  );
}
