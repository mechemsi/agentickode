// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { Clock, Save } from "lucide-react";
import { getAppSettings, updateAppSetting } from "../../api";
import { useToast } from "../shared/Toast";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface DayConfig {
  start: string;
  end: string;
}

interface ScheduleConfig {
  enabled: boolean;
  timezone: string;
  days: Record<string, DayConfig | null>;
}

const DEFAULT_SCHEDULE: ScheduleConfig = {
  enabled: false,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  days: {
    "0": { start: "20:00", end: "08:00" },
    "1": { start: "20:00", end: "08:00" },
    "2": { start: "20:00", end: "08:00" },
    "3": { start: "20:00", end: "08:00" },
    "4": { start: "20:00", end: "08:00" },
    "5": { start: "00:00", end: "23:59" },
    "6": { start: "00:00", end: "23:59" },
  },
};

const COMMON_TIMEZONES = [
  "UTC",
  "US/Eastern",
  "US/Central",
  "US/Mountain",
  "US/Pacific",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Vilnius",
  "Europe/Moscow",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Asia/Kolkata",
  "Australia/Sydney",
];

export default function QueueSchedule() {
  const [schedule, setSchedule] = useState<ScheduleConfig>(DEFAULT_SCHEDULE);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  useEffect(() => {
    getAppSettings()
      .then((settings) => {
        if (settings.queue_schedule && typeof settings.queue_schedule === "object") {
          setSchedule(settings.queue_schedule as ScheduleConfig);
        }
      })
      .catch(() => {/* ignore */});
  }, []);

  const update = (patch: Partial<ScheduleConfig>) => {
    setSchedule((prev) => ({ ...prev, ...patch }));
    setDirty(true);
  };

  const toggleDay = (dayKey: string) => {
    setSchedule((prev) => {
      const days = { ...prev.days };
      if (days[dayKey] === null) {
        days[dayKey] = { start: "20:00", end: "08:00" };
      } else {
        days[dayKey] = null;
      }
      return { ...prev, days };
    });
    setDirty(true);
  };

  const setDayTime = (dayKey: string, field: "start" | "end", value: string) => {
    setSchedule((prev) => {
      const days = { ...prev.days };
      const existing = days[dayKey];
      if (existing) {
        days[dayKey] = { ...existing, [field]: value };
      }
      return { ...prev, days };
    });
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateAppSetting("queue_schedule", schedule);
      toast.success("Queue schedule saved");
      setDirty(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save schedule");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Clock className="w-5 h-5 text-blue-400" />
          Queue Schedule
        </h2>
        {dirty && (
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? "Saving..." : "Save"}
          </button>
        )}
      </div>

      <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl p-5 backdrop-blur-sm space-y-4">
        {/* Master toggle */}
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={schedule.enabled}
            onChange={(e) => update({ enabled: e.target.checked })}
            className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500/40 focus:ring-offset-0"
          />
          <div>
            <span className="text-sm font-medium text-gray-200">Enable Queue Schedule</span>
            <p className="text-xs text-gray-500">
              Only dispatch runs during configured time windows. Runs created outside the window will wait.
            </p>
          </div>
        </label>

        {schedule.enabled && (
          <>
            {/* Timezone */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                Timezone
              </label>
              <input
                type="text"
                value={schedule.timezone}
                onChange={(e) => update({ timezone: e.target.value })}
                list="tz-list"
                className="w-full max-w-xs bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40"
              />
              <datalist id="tz-list">
                {COMMON_TIMEZONES.map((tz) => (
                  <option key={tz} value={tz} />
                ))}
              </datalist>
            </div>

            {/* Day grid */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Allowed Hours
                <span className="text-gray-500 font-normal ml-1 text-xs">
                  per day (overnight windows supported, e.g. 20:00 - 08:00)
                </span>
              </label>
              <div className="space-y-2">
                {DAY_LABELS.map((label, idx) => {
                  const dayKey = String(idx);
                  const config = schedule.days[dayKey];
                  const enabled = config !== null && config !== undefined;
                  return (
                    <div key={dayKey} className="flex items-center gap-3">
                      <label className="flex items-center gap-2 w-20 shrink-0 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={enabled}
                          onChange={() => toggleDay(dayKey)}
                          className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500/40 focus:ring-offset-0"
                        />
                        <span className={`text-sm font-mono ${enabled ? "text-gray-200" : "text-gray-600"}`}>
                          {label}
                        </span>
                      </label>
                      {enabled && config && (
                        <div className="flex items-center gap-2">
                          <input
                            type="time"
                            value={config.start}
                            onChange={(e) => setDayTime(dayKey, "start", e.target.value)}
                            className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                          />
                          <span className="text-gray-500 text-xs">to</span>
                          <input
                            type="time"
                            value={config.end}
                            onChange={(e) => setDayTime(dayKey, "end", e.target.value)}
                            className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                          />
                        </div>
                      )}
                      {!enabled && (
                        <span className="text-xs text-gray-600 italic">disabled</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}