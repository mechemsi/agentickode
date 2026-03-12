// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { Globe, Server } from "lucide-react";

interface FormData {
  name: string;
  url: string;
}

const defaults: FormData = {
  name: "",
  url: "http://",
};

export default function OllamaServerForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: Partial<FormData>;
  onSubmit: (data: FormData) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<FormData>({ ...defaults, ...initial });

  const set = (key: keyof FormData, val: string) =>
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
          placeholder="gpu-01"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-gray-400 inline-flex items-center gap-1">
          <Globe className="w-3 h-3" />
          url
        </span>
        <input
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          value={form.url}
          onChange={(e) => set("url", e.target.value)}
          placeholder="http://10.10.50.20:11434"
        />
      </label>
      <div className="col-span-1 sm:col-span-2 flex gap-2 mt-2">
        <button
          onClick={() => onSubmit(form)}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm shadow-sm shadow-blue-900/30 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        >
          Save
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