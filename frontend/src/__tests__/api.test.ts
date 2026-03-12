// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock fetch globally
const mockFetch = vi.fn();
(globalThis as Record<string, unknown>).fetch = mockFetch;

// Import after mock setup
import {
  getRuns, getRun, approveRun, rejectRun,
  getStats, getProjects, deleteProject, getHealth,
} from "../api";

beforeEach(() => {
  mockFetch.mockReset();
});

describe("API client", () => {
  it("getRuns calls correct URL", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [] });
    const result = await getRuns();
    expect(result).toEqual([]);
    expect(mockFetch).toHaveBeenCalledWith("/api/runs");
  });

  it("getRuns with params", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [] });
    await getRuns("status=pending");
    expect(mockFetch).toHaveBeenCalledWith("/api/runs?status=pending");
  });

  it("getRun calls correct URL", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1 }) });
    const result = await getRun(1);
    expect(result).toEqual({ id: 1 });
  });

  it("approveRun sends POST", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ status: "approved" }) });
    await approveRun(5);
    expect(mockFetch).toHaveBeenCalledWith("/api/runs/5/approve", expect.objectContaining({ method: "POST" }));
  });

  it("rejectRun sends POST with body", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ status: "rejected" }) });
    await rejectRun(5, "bad code");
    const call = mockFetch.mock.calls[0];
    expect(JSON.parse(call[1].body)).toEqual({ reason: "bad code" });
  });

  it("getStats calls correct URL", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ total_runs: 0 }) });
    await getStats();
    expect(mockFetch).toHaveBeenCalledWith("/api/stats");
  });

  it("getProjects calls correct URL", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [] });
    await getProjects();
    expect(mockFetch).toHaveBeenCalledWith("/api/projects");
  });

  it("deleteProject sends DELETE", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true });
    await deleteProject("p1");
    expect(mockFetch).toHaveBeenCalledWith("/api/projects/p1", expect.objectContaining({ method: "DELETE" }));
  });

  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });
    await expect(getRuns()).rejects.toThrow("GET /runs: 500");
  });

  it("getHealth calls correct URL", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ status: "ok" }) });
    await getHealth();
    expect(mockFetch).toHaveBeenCalledWith("/api/health");
  });
});