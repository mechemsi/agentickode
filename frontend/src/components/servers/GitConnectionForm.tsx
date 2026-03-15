// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { Loader2, Save, X } from "lucide-react";
import type { GitConnection, GitConnectionCreate } from "../../types";

const PROVIDERS = [
  { value: "github", label: "GitHub" },
  { value: "gitea", label: "Gitea" },
  { value: "gitlab", label: "GitLab" },
  { value: "bitbucket", label: "Bitbucket" },
];

const SELF_HOSTED_PROVIDERS = new Set(["gitea", "gitlab"]);

interface Props {
  serverId: number;
  existing?: GitConnection;
  onSave: (data: GitConnectionCreate | Partial<GitConnectionCreate>) => Promise<void>;
  onCancel: () => void;
}

export default function GitConnectionForm({ serverId, existing, onSave, onCancel }: Props) {
  const [name, setName] = useState(existing?.name ?? "");
  const [provider, setProvider] = useState(existing?.provider ?? "github");
  const [baseUrl, setBaseUrl] = useState(existing?.base_url ?? "");
  const [token, setToken] = useState("");
  const [scope, setScope] = useState(existing?.scope ?? "server");
  const [isDefault, setIsDefault] = useState(existing?.is_default ?? false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showBaseUrl = SELF_HOSTED_PROVIDERS.has(provider);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (existing) {
        const update: Partial<GitConnectionCreate> = { name, provider, scope, is_default: isDefault };
        if (showBaseUrl) update.base_url = baseUrl || undefined;
        if (token) update.token = token;
        if (scope === "server") update.workspace_server_id = serverId;
        await onSave(update);
      } else {
        const create: GitConnectionCreate = {
          name,
          provider,
          token,
          scope,
          is_default: isDefault,
        };
        if (showBaseUrl && baseUrl) create.base_url = baseUrl;
        if (scope === "server") create.workspace_server_id = serverId;
        await onSave(create);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const canSubmit = name.trim() && (existing ? true : token.trim());

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && <p className="text-red-400 text-xs">{error}</p>}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. My GitHub Token"
            className="w-full px-2.5 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Provider</label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="w-full px-2.5 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50"
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
      </div>

      {showBaseUrl && (
        <div>
          <label className="block text-xs text-gray-400 mb-1">Base URL</label>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={provider === "gitea" ? "https://gitea.example.com" : "https://gitlab.example.com"}
            className="w-full px-2.5 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50"
          />
        </div>
      )}

      <div>
        <label className="block text-xs text-gray-400 mb-1">
          {existing ? "Token (leave empty to keep current)" : "Token"}
        </label>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder={existing ? "Token configured — enter new value to change" : "Personal access token"}
          className="w-full px-2.5 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Scope</label>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            className="w-full px-2.5 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50"
          >
            <option value="global">Global</option>
            <option value="server">This Server</option>
          </select>
        </div>
        <div className="flex items-end pb-1">
          <label className="inline-flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500/30"
            />
            Set as default
          </label>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-gray-400 hover:text-white rounded hover:bg-gray-700/50 transition-colors"
        >
          <X className="w-3.5 h-3.5 inline mr-1" />
          Cancel
        </button>
        <button
          type="submit"
          disabled={!canSubmit || saving}
          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-sm inline-flex items-center gap-1.5 transition-colors"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          {saving ? "Saving..." : existing ? "Update" : "Save"}
        </button>
      </div>
    </form>
  );
}
