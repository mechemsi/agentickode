// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { describe, it, expect, vi, afterEach } from "vitest";
import { formatDuration } from "../utils/formatDuration";

describe("formatDuration", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns null when startedAt is null", () => {
    expect(formatDuration(null, null)).toBeNull();
    expect(formatDuration(null, "2024-01-01T00:01:00Z")).toBeNull();
  });

  it("formats seconds only", () => {
    const start = "2024-01-01T00:00:00Z";
    const end = "2024-01-01T00:00:45Z";
    expect(formatDuration(start, end)).toBe("45s");
  });

  it("formats zero seconds", () => {
    const start = "2024-01-01T00:00:00Z";
    const end = "2024-01-01T00:00:00Z";
    expect(formatDuration(start, end)).toBe("0s");
  });

  it("formats minutes and seconds", () => {
    const start = "2024-01-01T00:00:00Z";
    const end = "2024-01-01T00:02:34Z";
    expect(formatDuration(start, end)).toBe("2m 34s");
  });

  it("formats whole minutes (0 remaining seconds)", () => {
    const start = "2024-01-01T00:00:00Z";
    const end = "2024-01-01T00:03:00Z";
    expect(formatDuration(start, end)).toBe("3m 0s");
  });

  it("formats hours and minutes", () => {
    const start = "2024-01-01T00:00:00Z";
    const end = "2024-01-01T01:05:00Z";
    expect(formatDuration(start, end)).toBe("1h 5m");
  });

  it("formats hours with zero remaining minutes", () => {
    const start = "2024-01-01T00:00:00Z";
    const end = "2024-01-01T02:00:00Z";
    expect(formatDuration(start, end)).toBe("2h 0m");
  });

  it("uses current time when completedAt is null (running phase)", () => {
    const now = new Date("2024-01-01T00:00:50Z").getTime();
    vi.setSystemTime(now);

    const start = "2024-01-01T00:00:00Z";
    expect(formatDuration(start, null)).toBe("50s");
  });

  it("running phase with elapsed minutes uses current time", () => {
    const now = new Date("2024-01-01T00:03:15Z").getTime();
    vi.setSystemTime(now);

    const start = "2024-01-01T00:00:00Z";
    expect(formatDuration(start, null)).toBe("3m 15s");
  });
});