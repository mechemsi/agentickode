// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConfirmProvider } from "../components/shared/ConfirmDialog";
import { ToastProvider } from "../components/shared/Toast";

const mockGetHealth = vi.fn().mockResolvedValue({
  status: "ok",
  services: [
    { name: "database", status: "ok", latency_ms: 2.5 },
    { name: "ollama", status: "ok", latency_ms: 15.0 },
    { name: "openhands", status: "error", latency_ms: 5000, error: "timeout" },
  ],
  worker_running: true,
  active_runs: 1,
});

const mockGetSSHKeys = vi.fn().mockResolvedValue([
  {
    name: "id_ed25519",
    public_key: "ssh-ed25519 AAAA agentickode@host",
    created_at: "2025-01-01T00:00:00Z",
    is_default: true,
  },
]);

const mockCreateSSHKey = vi.fn().mockResolvedValue({
  name: "new-key",
  public_key: "ssh-ed25519 BBBB new@host",
  created_at: "2025-01-02T00:00:00Z",
  is_default: false,
});

const mockDeleteSSHKey = vi.fn().mockResolvedValue(undefined);
const mockGetNotificationChannels = vi.fn().mockResolvedValue([]);
const mockGetAppSettings = vi.fn().mockResolvedValue({});
const mockUpdateAppSetting = vi.fn().mockResolvedValue(undefined);
const mockGetSupportedAgents = vi.fn().mockResolvedValue([
  { name: "claude", display_name: "Claude Code", description: "", agent_type: "cli_binary" },
  { name: "aider", display_name: "Aider", description: "", agent_type: "cli_binary" },
  { name: "gemini", display_name: "Gemini CLI", description: "", agent_type: "cli_binary" },
  { name: "openhands", display_name: "OpenHands", description: "", agent_type: "api_service" },
]);

vi.mock("../api", () => ({
  getHealth: (...args: unknown[]) => mockGetHealth(...args),
  getSSHKeys: (...args: unknown[]) => mockGetSSHKeys(...args),
  createSSHKey: (...args: unknown[]) => mockCreateSSHKey(...args),
  deleteSSHKey: (...args: unknown[]) => mockDeleteSSHKey(...args),
  getNotificationChannels: (...args: unknown[]) =>
    mockGetNotificationChannels(...args),
  getAppSettings: (...args: unknown[]) => mockGetAppSettings(...args),
  updateAppSetting: (...args: unknown[]) => mockUpdateAppSetting(...args),
  getSupportedAgents: (...args: unknown[]) => mockGetSupportedAgents(...args),
}));

import Settings from "../pages/Settings";

function renderSettings() {
  return render(
    <ConfirmProvider>
      <ToastProvider>
        <Settings />
      </ToastProvider>
    </ConfirmProvider>,
  );
}

describe("Settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetHealth.mockResolvedValue({
      status: "ok",
      services: [
        { name: "database", status: "ok", latency_ms: 2.5 },
        { name: "ollama", status: "ok", latency_ms: 15.0 },
        { name: "openhands", status: "error", latency_ms: 5000, error: "timeout" },
      ],
      worker_running: true,
      active_runs: 1,
    });
    mockGetSSHKeys.mockResolvedValue([
      {
        name: "id_ed25519",
        public_key: "ssh-ed25519 AAAA agentickode@host",
        created_at: "2025-01-01T00:00:00Z",
        is_default: true,
      },
    ]);
    mockGetAppSettings.mockResolvedValue({});
  });

  it("renders the heading", () => {
    renderSettings();
    expect(screen.getByText("Settings & Health")).toBeInTheDocument();
  });

  it("shows health status", async () => {
    renderSettings();
    expect(await screen.findByText("Overall:")).toBeInTheDocument();
    const okElements = await screen.findAllByText("ok");
    expect(okElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows service names", async () => {
    renderSettings();
    expect(await screen.findByText("database")).toBeInTheDocument();
    expect(await screen.findByText("ollama")).toBeInTheDocument();
    // "openhands" appears in both health services and default agents sections
    const openhands = await screen.findAllByText("openhands");
    expect(openhands.length).toBeGreaterThanOrEqual(1);
  });

  it("shows SSH Keys section", async () => {
    renderSettings();
    expect(await screen.findByText("SSH Keys")).toBeInTheDocument();
  });

  it("lists existing SSH keys", async () => {
    renderSettings();
    expect(await screen.findByText("id_ed25519")).toBeInTheDocument();
    expect(await screen.findByText("ssh-ed25519 AAAA agentickode@host")).toBeInTheDocument();
    expect(await screen.findByText("default")).toBeInTheDocument();
  });

  it("shows generate key form when button clicked", async () => {
    const user = userEvent.setup();
    renderSettings();
    const btn = await screen.findByText("Generate Key");
    await user.click(btn);
    expect(screen.getByPlaceholderText("e.g. my-server")).toBeInTheDocument();
  });

  it("shows empty state when no keys", async () => {
    mockGetSSHKeys.mockResolvedValue([]);
    renderSettings();
    expect(
      await screen.findByText("No SSH keys found. Keys are auto-generated on container start."),
    ).toBeInTheDocument();
  });
});