// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { FolderOpen, Globe, Key, Lock, Server, User, Users } from "lucide-react";

interface FormData {
  name: string;
  hostname: string;
  port: number;
  username: string;
  ssh_key_path: string;
  worker_user: string;
  workspace_root: string;
  setup_password: string;
  [key: string]: unknown;
}

const defaults: FormData = {
  name: "",
  hostname: "",
  port: 22,
  username: "root",
  ssh_key_path: "",
  worker_user: "coder",
  workspace_root: "",
  setup_password: "",
};

export default function WorkspaceServerForm({
  initial,
  onSubmit,
  onCancel,
  loading,
  isEdit,
}: {
  initial?: Partial<FormData>;
  onSubmit: (data: Record<string, unknown>) => void;
  onCancel: () => void;
  loading?: boolean;
  isEdit?: boolean;
}) {
  const [form, setForm] = useState<FormData>({ ...defaults, ...initial });

  const set = (key: keyof FormData, val: string | number) =>
    setForm((p) => ({ ...p, [key]: val }));

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-xs text-gray-400 inline-flex items-center gap-1">
          <Server className="w-3 h-3" />
          name
        </span>
        <input
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="coding-01"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-gray-400 inline-flex items-center gap-1">
          <Globe className="w-3 h-3" />
          hostname
        </span>
        <input
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          value={form.hostname}
          onChange={(e) => set("hostname", e.target.value)}
          placeholder="10.10.50.25"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-gray-400">port</span>
        <input
          type="number"
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          value={form.port}
          onChange={(e) => set("port", parseInt(e.target.value) || 22)}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-gray-400 inline-flex items-center gap-1">
          <User className="w-3 h-3" />
          SSH admin user
        </span>
        <input
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          value={form.username}
          onChange={(e) => set("username", e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-gray-400 inline-flex items-center gap-1">
          <Key className="w-3 h-3" />
          ssh_key_path
        </span>
        <input
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          value={form.ssh_key_path}
          onChange={(e) => set("ssh_key_path", e.target.value)}
          placeholder="(uses server default)"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-gray-400 inline-flex items-center gap-1">
          <Users className="w-3 h-3" />
          worker user
        </span>
        <input
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          value={form.worker_user}
          onChange={(e) => set("worker_user", e.target.value)}
          placeholder="coder"
        />
      </label>
      <label className="flex flex-col gap-1 sm:col-span-2">
        <span className="text-xs text-gray-400 inline-flex items-center gap-1">
          <FolderOpen className="w-3 h-3" />
          workspace folder
        </span>
        <input
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          value={form.workspace_root}
          onChange={(e) => set("workspace_root", e.target.value)}
          placeholder="/home/coder/workspaces (auto-created if empty)"
        />
      </label>
      {!isEdit && (
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-gray-400 inline-flex items-center gap-1">
            <Lock className="w-3 h-3" />
            SSH password (for initial key deployment)
          </span>
          <input
            type="password"
            className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            value={form.setup_password}
            onChange={(e) => set("setup_password", e.target.value)}
            placeholder="leave empty if SSH key is already deployed"
            autoComplete="off"
          />
          <span className="text-[10px] text-gray-500">
            Used once to deploy the SSH key. Not stored.
          </span>
        </label>
      )}
      <div className="col-span-1 sm:col-span-2 flex gap-2 mt-2">
        <button
          onClick={() => {
            const { setup_password, workspace_root, ...rest } = form;
            const data: Record<string, unknown> = { ...rest };
            if (workspace_root) data.workspace_root = workspace_root;
            if (setup_password) data.setup_password = setup_password;
            onSubmit(data);
          }}
          disabled={loading}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg text-sm shadow-sm shadow-blue-900/30 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        >
          {loading ? "Saving..." : "Save"}
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-1.5 text-gray-400 hover:text-white text-sm rounded-lg hover:bg-gray-700/50 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}