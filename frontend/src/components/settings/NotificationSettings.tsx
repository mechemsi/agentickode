// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { Bell, Pencil, Plus, Send, Trash2 } from "lucide-react";
import {
  createNotificationChannel,
  deleteNotificationChannel,
  getNotificationChannels,
  testNotificationChannel,
  updateNotificationChannel,
} from "../../api";
import type { NotificationChannel } from "../../types";
import { useConfirm } from "../shared/ConfirmDialog";
import { useToast } from "../shared/Toast";
import NotificationChannelForm from "./NotificationChannelForm";

const typeIcon: Record<string, string> = {
  telegram: "TG",
  slack: "SL",
  discord: "DC",
  webhook: "WH",
};

const typeColor: Record<string, string> = {
  telegram: "text-sky-400 bg-sky-500/10",
  slack: "text-purple-400 bg-purple-500/10",
  discord: "text-indigo-400 bg-indigo-500/10",
  webhook: "text-orange-400 bg-orange-500/10",
};

export default function NotificationSettings() {
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState<number | null>(null);
  const toast = useToast();
  const confirm = useConfirm();

  const load = async () => {
    try {
      setChannels(await getNotificationChannels());
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (data: Record<string, unknown>) => {
    setLoading(true);
    try {
      await createNotificationChannel(
        data as unknown as Parameters<typeof createNotificationChannel>[0],
      );
      setAdding(false);
      toast.success("Channel created");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create channel");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async (id: number, data: Record<string, unknown>) => {
    try {
      await updateNotificationChannel(
        id,
        data as unknown as Parameters<typeof updateNotificationChannel>[1],
      );
      setEditing(null);
      toast.success("Channel updated");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update channel");
    }
  };

  const handleDelete = async (id: number) => {
    const ok = await confirm({
      title: "Delete Channel",
      message:
        "Delete this notification channel? Notifications will stop being sent.",
      confirmLabel: "Delete",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await deleteNotificationChannel(id);
      toast.success("Channel deleted");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete channel");
    }
  };

  const handleTest = async (id: number) => {
    setTesting(id);
    try {
      const result = await testNotificationChannel(id);
      if (result.success) {
        toast.success("Test notification sent!");
      } else {
        toast.error(`Test failed: ${result.error}`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Test failed");
    } finally {
      setTesting(null);
    }
  };

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Bell className="w-5 h-5 text-blue-400" />
          Notifications
        </h2>
        <button
          onClick={() => setAdding(!adding)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          Add Channel
        </button>
      </div>

      {adding && (
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 mb-4 backdrop-blur-sm animate-fade-in">
          <NotificationChannelForm
            onSubmit={handleCreate}
            onCancel={() => setAdding(false)}
            loading={loading}
          />
        </div>
      )}

      {channels.length === 0 && !adding ? (
        <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-6 text-center text-sm text-gray-500">
          No notification channels configured. Add a channel to get alerts for
          task events.
        </div>
      ) : (
        <div className="space-y-3">
          {channels.map((ch) => (
            <div
              key={ch.id}
              className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-4 backdrop-blur-sm group hover:border-gray-700/60 transition-all"
            >
              {editing === ch.id ? (
                <NotificationChannelForm
                  initial={ch}
                  onSubmit={(data) => handleUpdate(ch.id, data)}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <>
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-3">
                      <span
                        className={`text-xs font-mono font-semibold px-2 py-0.5 rounded-md ${typeColor[ch.channel_type] ?? "text-gray-400 bg-gray-700/50"}`}
                      >
                        {typeIcon[ch.channel_type] ?? ch.channel_type}
                      </span>
                      <span className="font-medium text-white">{ch.name}</span>
                      {!ch.enabled && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-700/50 text-gray-500">
                          disabled
                        </span>
                      )}
                    </div>
                    <div className="flex gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleTest(ch.id)}
                        disabled={testing === ch.id}
                        className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors disabled:opacity-50"
                      >
                        <Send className="w-3 h-3" />
                        {testing === ch.id ? "Sending..." : "Test"}
                      </button>
                      <button
                        onClick={() => setEditing(ch.id)}
                        className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700/50 transition-colors"
                      >
                        <Pencil className="w-3 h-3" />
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(ch.id)}
                        className="text-xs text-red-400 hover:text-red-300 inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-red-900/20 transition-colors"
                      >
                        <Trash2 className="w-3 h-3" />
                        Delete
                      </button>
                    </div>
                  </div>
                  {ch.events.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {ch.events.map((ev) => (
                        <span
                          key={ev}
                          className="text-xs px-2 py-0.5 rounded-md bg-gray-800 text-gray-400 border border-gray-700/50"
                        >
                          {ev.replace("_", " ")}
                        </span>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}