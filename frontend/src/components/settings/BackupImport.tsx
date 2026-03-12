// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useRef, useState } from "react";
import { Upload, AlertCircle, CheckCircle2, SkipForward } from "lucide-react";
import { importConfig, importPreview } from "../../api";
import type {
  ConflictResolution,
  ImportOptions,
  ImportResult,
  PreviewResult,
} from "../../types";
import { useToast } from "../shared/Toast";

const ENTITY_LABELS: Record<string, string> = {
  workspace_servers: "Workspace Servers",
  ollama_servers: "Ollama Servers",
  app_settings: "App Settings",
  agent_settings: "Agent Settings",
  notification_channels: "Notification Channels",
  workflow_templates: "Workflow Templates",
  project_configs: "Projects",
  role_configs: "Role Configs",
  role_assignments: "Role Assignments",
};

export default function BackupImport() {
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [conflict, setConflict] = useState<ConflictResolution>("skip");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const handleFileSelect = async (f: File) => {
    setFile(f);
    setResult(null);
    setPreview(null);
    setLoading(true);
    try {
      const opts: ImportOptions = {
        conflict_resolution: conflict,
        encryption_password: password || undefined,
      };
      const p = await importPreview(f, opts);
      setPreview(p);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const opts: ImportOptions = {
        conflict_resolution: conflict,
        encryption_password: password || undefined,
      };
      const r = await importConfig(file, opts);
      setResult(r);
      setPreview(null);
      toast.success("Import completed");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setLoading(false);
    }
  };

  const totalPreviewItems = preview
    ? Object.values(preview.entities).reduce((s, items) => s + items.length, 0)
    : 0;

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
        <Upload className="w-5 h-5 text-blue-400" />
        Import Configuration
      </h2>
      <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 backdrop-blur-sm space-y-4">
        {/* Password */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Decryption Password <span className="text-gray-500">(if encrypted)</span>
          </label>
          <input
            type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter password..."
            className="w-full max-w-xs px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          />
        </div>

        {/* Conflict resolution */}
        <div>
          <label className="block text-xs text-gray-400 mb-2">On Conflict</label>
          <div className="flex gap-3">
            {(["skip", "overwrite"] as ConflictResolution[]).map((c) => (
              <label key={c} className="flex items-center gap-1.5 text-sm text-gray-300 cursor-pointer">
                <input
                  type="radio" name="conflict" value={c}
                  checked={conflict === c}
                  onChange={() => setConflict(c)}
                  className="accent-blue-500"
                />
                {c === "skip" && <><SkipForward className="w-3.5 h-3.5" /> Skip existing</>}
                {c === "overwrite" && <><AlertCircle className="w-3.5 h-3.5" /> Overwrite</>}
              </label>
            ))}
          </div>
        </div>

        {/* File upload */}
        <div>
          <input
            ref={fileRef} type="file" accept=".json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFileSelect(f);
            }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={loading}
            className="flex items-center gap-1.5 px-4 py-2 text-sm bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            <Upload className="w-4 h-4" />
            {file ? file.name : "Select backup file..."}
          </button>
        </div>

        {/* Preview */}
        {preview && totalPreviewItems > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-300">Preview</h3>
            <div className="bg-gray-800/50 rounded-lg p-3 space-y-1.5">
              {Object.entries(preview.entities).map(([key, items]) =>
                items.length > 0 ? (
                  <div key={key} className="flex items-center justify-between text-xs">
                    <span className="text-gray-400">{ENTITY_LABELS[key] || key}</span>
                    <span className="flex gap-2">
                      {items.filter((i) => i.action === "create").length > 0 && (
                        <span className="text-green-400">
                          +{items.filter((i) => i.action === "create").length} new
                        </span>
                      )}
                      {items.filter((i) => i.action === "update").length > 0 && (
                        <span className="text-yellow-400">
                          ~{items.filter((i) => i.action === "update").length} update
                        </span>
                      )}
                    </span>
                  </div>
                ) : null,
              )}
            </div>
            <button
              onClick={handleImport}
              disabled={loading}
              className="flex items-center gap-1.5 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              <Upload className="w-4 h-4" />
              {loading ? "Importing..." : "Import"}
            </button>
          </div>
        )}

        {preview && totalPreviewItems === 0 && (
          <p className="text-sm text-gray-500">No entities found in file.</p>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-green-400 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4" /> Import Complete
            </h3>
            <div className="bg-gray-800/50 rounded-lg p-3 space-y-1.5">
              {Object.entries(result.entities).map(([key, stats]) => (
                <div key={key} className="flex items-center justify-between text-xs">
                  <span className="text-gray-400">{ENTITY_LABELS[key] || key}</span>
                  <span className="flex gap-2">
                    {stats.created > 0 && <span className="text-green-400">+{stats.created}</span>}
                    {stats.updated > 0 && <span className="text-yellow-400">~{stats.updated}</span>}
                    {stats.skipped > 0 && <span className="text-gray-500">-{stats.skipped}</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}