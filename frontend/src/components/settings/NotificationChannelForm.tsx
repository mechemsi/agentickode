// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { CHANNEL_TYPES, NOTIFICATION_EVENTS } from "../../types";
import type { NotificationChannel } from "../../types";

interface Props {
  initial?: Partial<NotificationChannel>;
  onSubmit: (data: Record<string, unknown>) => void;
  onCancel: () => void;
  loading?: boolean;
}

const CONFIG_FIELDS: Record<
  string,
  { label: string; key: string; type?: string; placeholder: string }[]
> = {
  telegram: [
    {
      label: "Bot Token",
      key: "bot_token",
      placeholder: "123456:ABC-DEF...",
    },
    { label: "Chat ID", key: "chat_id", placeholder: "-1001234567890" },
  ],
  slack: [
    {
      label: "Webhook URL",
      key: "webhook_url",
      placeholder: "https://hooks.slack.com/services/...",
    },
  ],
  discord: [
    {
      label: "Webhook URL",
      key: "webhook_url",
      placeholder: "https://discord.com/api/webhooks/...",
    },
  ],
  webhook: [
    { label: "URL", key: "url", placeholder: "https://example.com/hook" },
    { label: "Method", key: "method", placeholder: "POST" },
    {
      label: "Headers (JSON)",
      key: "headers",
      placeholder: '{"Authorization": "Bearer ..."}',
    },
  ],
};

const EVENT_LABELS: Record<string, string> = {
  run_started: "Run Started",
  run_completed: "Run Completed",
  run_failed: "Run Failed",
  approval_requested: "Approval Requested",
};

export default function NotificationChannelForm({
  initial,
  onSubmit,
  onCancel,
  loading,
}: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [channelType, setChannelType] = useState(
    initial?.channel_type ?? "telegram",
  );
  const [config, setConfig] = useState<Record<string, string>>(
    (initial?.config as Record<string, string>) ?? {},
  );
  const [events, setEvents] = useState<string[]>(initial?.events ?? []);
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);

  const toggleEvent = (ev: string) => {
    setEvents((prev) =>
      prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev],
    );
  };

  const handleConfigChange = (key: string, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = () => {
    let finalConfig = { ...config };
    if (channelType === "webhook" && config.headers) {
      try {
        finalConfig = {
          ...finalConfig,
          headers: JSON.parse(config.headers),
        };
      } catch {
        /* keep as string if invalid JSON */
      }
    }
    onSubmit({ name, channel_type: channelType, config: finalConfig, events, enabled });
  };

  const fields = CONFIG_FIELDS[channelType] ?? [];

  return (
    <div className="space-y-4">
      {/* Name */}
      <div>
        <label className="block text-xs text-gray-400 mb-1">Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My Telegram Channel"
          className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        />
      </div>

      {/* Channel Type */}
      <div>
        <label className="block text-xs text-gray-400 mb-1">Type</label>
        <select
          value={channelType}
          onChange={(e) => {
            setChannelType(e.target.value as typeof channelType);
            setConfig({});
          }}
          className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        >
          {CHANNEL_TYPES.map((t) => (
            <option key={t} value={t}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {/* Dynamic config fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {fields.map((f) => (
          <div key={f.key}>
            <label className="block text-xs text-gray-400 mb-1">
              {f.label}
            </label>
            <input
              type={f.type ?? "text"}
              value={config[f.key] ?? ""}
              onChange={(e) => handleConfigChange(f.key, e.target.value)}
              placeholder={f.placeholder}
              className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            />
          </div>
        ))}
      </div>

      {/* Events */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5">Events</label>
        <div className="flex flex-wrap gap-2">
          {NOTIFICATION_EVENTS.map((ev) => (
            <button
              key={ev}
              type="button"
              onClick={() => toggleEvent(ev)}
              className={`px-2.5 py-1 rounded-lg text-xs border transition-colors ${
                events.includes(ev)
                  ? "bg-blue-600/20 border-blue-500/40 text-blue-300"
                  : "bg-gray-800 border-gray-700 text-gray-500 hover:text-gray-300"
              }`}
            >
              {EVENT_LABELS[ev] ?? ev}
            </button>
          ))}
        </div>
      </div>

      {/* Enabled toggle */}
      <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="w-4 h-4 rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-blue-500/40"
        />
        Enabled
      </label>

      {/* Actions */}
      <div className="flex gap-2 justify-end pt-1">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={loading || !name.trim()}
          className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          {loading ? "Saving..." : initial ? "Update" : "Create"}
        </button>
      </div>
    </div>
  );
}