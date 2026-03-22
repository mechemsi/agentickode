// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  Send,
  Server,
  Trash2,
  X,
} from "lucide-react";
import {
  createServerGroup,
  deleteServerGroup,
  deployServerGroupSSHKey,
  deployServerGroupToken,
  getServerGroups,
  setServerGroupToken,
  updateServerGroup,
} from "../../api/servers";
import { useConfirm } from "../shared/ConfirmDialog";
import { useToast } from "../shared/Toast";
import type { ServerGroup } from "../../types";

interface Props {
  onGroupsChanged?: () => void;
}

const PROVIDER_OPTIONS = [
  { value: "github", label: "GitHub" },
  { value: "gitea", label: "Gitea" },
  { value: "gitlab", label: "GitLab" },
  { value: "bitbucket", label: "Bitbucket" },
];

export default function ServerGroupPanel({ onGroupsChanged }: Props) {
  const [groups, setGroups] = useState<ServerGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [tokenGroupId, setTokenGroupId] = useState<number | null>(null);
  const [tokenValue, setTokenValue] = useState("");
  const [tokenProvider, setTokenProvider] = useState("github");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const toast = useToast();
  const confirm = useConfirm();

  const load = async () => {
    try {
      const data = await getServerGroups();
      setGroups(data);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load groups");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async () => {
    if (!formName.trim()) return;
    setBusyAction("create");
    try {
      await createServerGroup({ name: formName.trim(), description: formDesc.trim() || undefined });
      setAdding(false);
      setFormName("");
      setFormDesc("");
      toast.success("Server group created");
      load();
      onGroupsChanged?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create group");
    } finally {
      setBusyAction(null);
    }
  };

  const handleUpdate = async (id: number) => {
    if (!formName.trim()) return;
    setBusyAction(`update-${id}`);
    try {
      await updateServerGroup(id, { name: formName.trim(), description: formDesc.trim() || undefined });
      setEditingId(null);
      setFormName("");
      setFormDesc("");
      toast.success("Group updated");
      load();
      onGroupsChanged?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update group");
    } finally {
      setBusyAction(null);
    }
  };

  const handleDelete = async (id: number) => {
    const ok = await confirm({
      title: "Delete Server Group",
      message: "Delete this server group? Servers will be unlinked but not deleted.",
      confirmLabel: "Delete",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await deleteServerGroup(id);
      toast.success("Group deleted");
      load();
      onGroupsChanged?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete group");
    }
  };

  const handleSetToken = async (id: number) => {
    if (!tokenValue.trim()) return;
    setBusyAction(`token-${id}`);
    try {
      await setServerGroupToken(id, tokenValue.trim(), tokenProvider);
      setTokenGroupId(null);
      setTokenValue("");
      toast.success("Token saved (encrypted)");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to set token");
    } finally {
      setBusyAction(null);
    }
  };

  const handleDeployToken = async (id: number) => {
    setBusyAction(`deploy-token-${id}`);
    try {
      const resp = await deployServerGroupToken(id);
      const ok = resp.results.filter((r) => r.success).length;
      const fail = resp.results.filter((r) => !r.success).length;
      if (fail === 0) {
        toast.success(`Token deployed to ${ok} server(s)`);
      } else {
        toast.error(`Deployed: ${ok}, Failed: ${fail}`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Deploy failed");
    } finally {
      setBusyAction(null);
    }
  };

  const handleDeploySSHKey = async (id: number) => {
    setBusyAction(`deploy-key-${id}`);
    try {
      const resp = await deployServerGroupSSHKey(id);
      const ok = resp.results.filter((r) => r.success).length;
      const fail = resp.results.filter((r) => !r.success).length;
      if (fail === 0) {
        toast.success(`SSH key distributed to ${ok} server(s)`);
      } else {
        toast.error(`OK: ${ok}, Failed: ${fail}`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "SSH key deploy failed");
    } finally {
      setBusyAction(null);
    }
  };

  const startEdit = (g: ServerGroup) => {
    setEditingId(g.id);
    setFormName(g.name);
    setFormDesc(g.description || "");
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-sm py-4">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading server groups...
      </div>
    );
  }

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <Server className="w-4 h-4 text-purple-400" />
          Server Groups
        </h2>
        <button
          onClick={() => { setAdding(true); setFormName(""); setFormDesc(""); }}
          className="px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs inline-flex items-center gap-1.5 transition-colors"
        >
          <Plus className="w-3 h-3" />
          New Group
        </button>
      </div>

      {adding && (
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-3 mb-3 animate-fade-in">
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              placeholder="Group name"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              className="flex-1 px-2.5 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-purple-500/50"
            />
            <input
              type="text"
              placeholder="Description (optional)"
              value={formDesc}
              onChange={(e) => setFormDesc(e.target.value)}
              className="flex-1 px-2.5 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-purple-500/50"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setAdding(false)}
              className="px-3 py-1 text-xs text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={!formName.trim() || busyAction === "create"}
              className="px-3 py-1 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded text-xs transition-colors"
            >
              {busyAction === "create" ? "Creating..." : "Create"}
            </button>
          </div>
        </div>
      )}

      {groups.length === 0 && !adding && (
        <p className="text-xs text-gray-500 py-2">No server groups yet. Create one to share SSH keys and git tokens across servers.</p>
      )}

      <div className="space-y-2">
        {groups.map((g) => (
          <div
            key={g.id}
            className="bg-gray-900/40 border border-gray-800/60 rounded-lg p-3 hover:border-gray-700/60 transition-all"
          >
            {editingId === g.id ? (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="flex-1 px-2.5 py-1 bg-gray-900 border border-gray-700 rounded text-sm text-white focus:outline-none focus:ring-1 focus:ring-purple-500/50"
                />
                <input
                  type="text"
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  className="flex-1 px-2.5 py-1 bg-gray-900 border border-gray-700 rounded text-sm text-white focus:outline-none focus:ring-1 focus:ring-purple-500/50"
                />
                <button
                  onClick={() => handleUpdate(g.id)}
                  disabled={busyAction === `update-${g.id}`}
                  className="px-3 py-1 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded text-xs"
                >
                  Save
                </button>
                <button
                  onClick={() => setEditingId(null)}
                  className="text-gray-400 hover:text-white p-1"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setExpandedId(expandedId === g.id ? null : g.id)}
                      className="text-gray-400 hover:text-white"
                    >
                      {expandedId === g.id ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    </button>
                    <span className="text-sm font-medium text-white">{g.name}</span>
                    {g.description && (
                      <span className="text-xs text-gray-500">{g.description}</span>
                    )}
                    <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700/50 text-gray-400">
                      {g.server_count} server{g.server_count !== 1 ? "s" : ""}
                    </span>
                    {g.has_git_token && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-green-900/30 text-green-400 inline-flex items-center gap-1">
                        <KeyRound className="w-2.5 h-2.5" />
                        {g.git_provider_type || "token"}
                      </span>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => startEdit(g)}
                      className="text-xs text-gray-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => handleDelete(g.id)}
                      className="text-xs text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-red-900/20 transition-colors"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                {expandedId === g.id && (
                  <div className="mt-3 pt-3 border-t border-gray-700/40 space-y-3 animate-fade-in">
                    {/* Token management */}
                    <div>
                      <h4 className="text-xs text-gray-400 mb-2 font-medium">Git Token</h4>
                      {tokenGroupId === g.id ? (
                        <div className="flex gap-2 items-center">
                          <select
                            value={tokenProvider}
                            onChange={(e) => setTokenProvider(e.target.value)}
                            className="px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-purple-500/50"
                          >
                            {PROVIDER_OPTIONS.map((p) => (
                              <option key={p.value} value={p.value}>{p.label}</option>
                            ))}
                          </select>
                          <input
                            type="password"
                            placeholder="Git token / PAT"
                            value={tokenValue}
                            onChange={(e) => setTokenValue(e.target.value)}
                            className="flex-1 px-2.5 py-1 bg-gray-900 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-purple-500/50"
                          />
                          <button
                            onClick={() => handleSetToken(g.id)}
                            disabled={!tokenValue.trim() || busyAction === `token-${g.id}`}
                            className="px-3 py-1 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded text-xs transition-colors"
                          >
                            {busyAction === `token-${g.id}` ? "Saving..." : "Save"}
                          </button>
                          <button
                            onClick={() => { setTokenGroupId(null); setTokenValue(""); }}
                            className="text-gray-400 hover:text-white p-1"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <button
                            onClick={() => { setTokenGroupId(g.id); setTokenValue(""); setTokenProvider(g.git_provider_type || "github"); }}
                            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs inline-flex items-center gap-1 transition-colors"
                          >
                            <KeyRound className="w-3 h-3" />
                            {g.has_git_token ? "Update Token" : "Set Token"}
                          </button>
                          {g.has_git_token && (
                            <button
                              onClick={() => handleDeployToken(g.id)}
                              disabled={busyAction === `deploy-token-${g.id}`}
                              className="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded text-xs inline-flex items-center gap-1 transition-colors"
                            >
                              {busyAction === `deploy-token-${g.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                              Deploy Token to Servers
                            </button>
                          )}
                        </div>
                      )}
                    </div>

                    {/* SSH Key distribution */}
                    <div>
                      <h4 className="text-xs text-gray-400 mb-2 font-medium">SSH Key Distribution</h4>
                      <button
                        onClick={() => handleDeploySSHKey(g.id)}
                        disabled={busyAction === `deploy-key-${g.id}` || g.server_count === 0}
                        className="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white rounded text-xs inline-flex items-center gap-1 transition-colors"
                      >
                        {busyAction === `deploy-key-${g.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <KeyRound className="w-3 h-3" />}
                        Generate & Distribute SSH Key
                      </button>
                      <p className="text-xs text-gray-500 mt-1">
                        Generates an SSH key on the first server and distributes the public key to all others in the group.
                      </p>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
