// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { Eye, EyeOff, Plus, Trash2 } from "lucide-react";

export interface KVEntry {
  key: string;
  value: string;
}

export function parseKV(obj: Record<string, string | boolean> | null | undefined): KVEntry[] {
  if (!obj) return [];
  return Object.entries(obj).map(([key, value]) => ({
    key,
    value: String(value),
  }));
}

export function kvToObject(entries: KVEntry[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const { key, value } of entries) {
    if (key.trim()) result[key.trim()] = value;
  }
  return result;
}

interface KVEditorProps {
  entries: KVEntry[];
  onChange: (entries: KVEntry[]) => void;
  maskValues?: boolean;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
}

export function KVEditor({
  entries,
  onChange,
  maskValues = false,
  keyPlaceholder = "KEY",
  valuePlaceholder = "value",
}: KVEditorProps) {
  const [revealed, setRevealed] = useState<Set<number>>(new Set());

  const addRow = () => onChange([...entries, { key: "", value: "" }]);

  const removeRow = (idx: number) => {
    onChange(entries.filter((_, i) => i !== idx));
    setRevealed((prev) => {
      const next = new Set(prev);
      next.delete(idx);
      return next;
    });
  };

  const updateRow = (idx: number, field: "key" | "value", val: string) => {
    const updated = entries.map((e, i) => (i === idx ? { ...e, [field]: val } : e));
    onChange(updated);
  };

  const toggleReveal = (idx: number) => {
    setRevealed((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <div className="space-y-1.5">
      {entries.map((entry, idx) => (
        <div key={idx} className="flex gap-2 items-center">
          <input
            type="text"
            value={entry.key}
            onChange={(e) => updateRow(idx, "key", e.target.value)}
            placeholder={keyPlaceholder}
            className="flex-1 px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          />
          <input
            type={maskValues && !revealed.has(idx) ? "password" : "text"}
            value={entry.value}
            onChange={(e) => updateRow(idx, "value", e.target.value)}
            placeholder={valuePlaceholder}
            className="flex-1 px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-white font-mono placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          />
          {maskValues && (
            <button
              type="button"
              onClick={() => toggleReveal(idx)}
              className="text-gray-500 hover:text-gray-300 transition-colors"
              title={revealed.has(idx) ? "Hide value" : "Reveal value"}
            >
              {revealed.has(idx) ? (
                <EyeOff className="w-3.5 h-3.5" />
              ) : (
                <Eye className="w-3.5 h-3.5" />
              )}
            </button>
          )}
          <button
            type="button"
            onClick={() => removeRow(idx)}
            className="text-gray-600 hover:text-red-400 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={addRow}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors mt-1"
      >
        <Plus className="w-3 h-3" />
        Add
      </button>
    </div>
  );
}