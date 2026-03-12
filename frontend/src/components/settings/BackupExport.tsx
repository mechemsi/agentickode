// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { Download, Lock, Eye, EyeOff } from "lucide-react";
import { exportConfig } from "../../api";
import type { SecretMode, ExportRequest } from "../../types";
import { useToast } from "../shared/Toast";

const ENTITY_TYPES = [
  { key: "workspace_servers", label: "Workspace Servers" },
  { key: "ollama_servers", label: "Ollama Servers" },
  { key: "app_settings", label: "App Settings" },
  { key: "agent_settings", label: "Agent Settings" },
  { key: "notification_channels", label: "Notification Channels" },
  { key: "workflow_templates", label: "Workflow Templates" },
  { key: "project_configs", label: "Projects" },
  { key: "role_configs", label: "Role Configs" },
  { key: "role_assignments", label: "Role Assignments" },
];

export default function BackupExport() {
  const [secretMode, setSecretMode] = useState<SecretMode>("redacted");
  const [password, setPassword] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [projectId, setProjectId] = useState("");
  const [exporting, setExporting] = useState(false);
  const toast = useToast();

  const toggleType = (key: string) => {
    setSelectedTypes((prev) =>
      prev.includes(key) ? prev.filter((t) => t !== key) : [...prev, key],
    );
  };

  const handleExport = async () => {
    if (secretMode === "encrypted" && !password) {
      toast.error("Password required for encrypted export");
      return;
    }
    setExporting(true);
    try {
      const req: ExportRequest = {
        secret_mode: secretMode,
        encryption_password: secretMode === "encrypted" ? password : undefined,
        entity_types: selectedTypes.length > 0 ? selectedTypes : undefined,
        project_id: projectId || undefined,
      };
      const blob = await exportConfig(req);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `autodev-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Configuration exported");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
        <Download className="w-5 h-5 text-green-400" />
        Export Configuration
      </h2>
      <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 backdrop-blur-sm space-y-4">
        {/* Secret mode */}
        <div>
          <label className="block text-xs text-gray-400 mb-2">Secret Handling</label>
          <div className="flex gap-3">
            {(["redacted", "encrypted", "plaintext"] as SecretMode[]).map((m) => (
              <label key={m} className="flex items-center gap-1.5 text-sm text-gray-300 cursor-pointer">
                <input
                  type="radio" name="secretMode" value={m}
                  checked={secretMode === m}
                  onChange={() => setSecretMode(m)}
                  className="accent-blue-500"
                />
                {m === "redacted" && <><EyeOff className="w-3.5 h-3.5" /> Redacted</>}
                {m === "encrypted" && <><Lock className="w-3.5 h-3.5" /> Encrypted</>}
                {m === "plaintext" && <><Eye className="w-3.5 h-3.5" /> Plaintext</>}
              </label>
            ))}
          </div>
        </div>

        {/* Password for encrypted */}
        {secretMode === "encrypted" && (
          <div>
            <label className="block text-xs text-gray-400 mb-1">Encryption Password</label>
            <input
              type="password" value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password..."
              className="w-full max-w-xs px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            />
          </div>
        )}

        {/* Entity type selection */}
        <div>
          <label className="block text-xs text-gray-400 mb-2">
            Entity Types <span className="text-gray-500">(empty = all)</span>
          </label>
          <div className="flex flex-wrap gap-2">
            {ENTITY_TYPES.map((et) => (
              <button
                key={et.key}
                onClick={() => toggleType(et.key)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                  selectedTypes.includes(et.key)
                    ? "border-blue-500 bg-blue-500/20 text-blue-300"
                    : "border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600"
                }`}
              >
                {et.label}
              </button>
            ))}
          </div>
        </div>

        {/* Optional project filter */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Single Project Export <span className="text-gray-500">(optional)</span>
          </label>
          <input
            type="text" value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            placeholder="project_id..."
            className="w-full max-w-xs px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          />
        </div>

        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex items-center gap-1.5 px-4 py-2 text-sm bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          <Download className="w-4 h-4" />
          {exporting ? "Exporting..." : "Export"}
        </button>
      </div>
    </div>
  );
}