// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConfirmProvider } from "../components/shared/ConfirmDialog";
import { ToastProvider } from "../components/shared/Toast";
import AgentSettingsPage from "../pages/AgentSettings";

const mockGetAgents = vi.fn();
const mockUpdateAgent = vi.fn();
const mockGetAgentAvailability = vi.fn();

vi.mock("../api", () => ({
  getAgents: (...args: unknown[]) => mockGetAgents(...args),
  updateAgent: (...args: unknown[]) => mockUpdateAgent(...args),
  getAgentAvailability: (...args: unknown[]) => mockGetAgentAvailability(...args),
}));

const makeAgent = (overrides: Partial<{
  agent_name: string;
  display_name: string;
  description: string;
  supports_session: boolean;
  default_timeout: number;
  max_retries: number;
  environment_vars: Record<string, string>;
  cli_flags: Record<string, string | boolean>;
  command_templates: Record<string, string | boolean>;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
  id: number;
}> = {}) => ({
  id: 1,
  agent_name: "claude",
  display_name: "Claude CLI",
  description: "Anthropic Claude Code CLI agent",
  supports_session: true,
  default_timeout: 600,
  max_retries: 1,
  environment_vars: {},
  cli_flags: {},
  command_templates: {},
  enabled: true,
  agent_type: "cli_binary",
  install_cmd: null,
  check_cmd: null,
  prereq_check: null,
  prereq_name: null,
  needs_non_root: false,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
  ...overrides,
});

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <ConfirmProvider>
      <ToastProvider>{children}</ToastProvider>
    </ConfirmProvider>
  );
}

describe("AgentSettings page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetAgents.mockResolvedValue([makeAgent()]);
    mockGetAgentAvailability.mockResolvedValue([]);
    mockUpdateAgent.mockResolvedValue(makeAgent());
  });

  it("renders page heading", () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(screen.getByText("Agents")).toBeInTheDocument();
  });

  it("renders agent card with display name", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(await screen.findByText("Claude CLI")).toBeInTheDocument();
  });

  it("renders agent name badge", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(await screen.findByText("claude")).toBeInTheDocument();
  });

  it("shows disabled badge when agent is disabled", async () => {
    mockGetAgents.mockResolvedValue([makeAgent({ enabled: false })]);
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(await screen.findByText("Disabled")).toBeInTheDocument();
  });

  it("shows session badge when supports_session is true", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(await screen.findByText("Sessions")).toBeInTheDocument();
  });

  it("does not show session badge for non-session agents", async () => {
    mockGetAgents.mockResolvedValue([makeAgent({ supports_session: false })]);
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    await screen.findByText("Claude CLI");
    expect(screen.queryByText("Sessions")).not.toBeInTheDocument();
  });

  it("expands card on click and shows timeout input", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(screen.getByText("Default timeout (seconds)")).toBeInTheDocument();
  });

  it("expands card and shows max retries input", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(screen.getByText("Max retries")).toBeInTheDocument();
  });

  it("expands card and shows session support toggle", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(screen.getByText("Session support")).toBeInTheDocument();
  });

  it("expands card and shows CLI Flags section", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(screen.getByText("CLI Flags")).toBeInTheDocument();
  });

  it("expands card and shows Environment Variables section", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(screen.getByText("Environment Variables")).toBeInTheDocument();
  });

  it("expands card and shows Installation section", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(screen.getByText("Installation")).toBeInTheDocument();
  });

  it("expands card and shows Save button", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(screen.getByText("Save")).toBeInTheDocument();
  });

  it("save button calls updateAgent API", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);

    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(mockUpdateAgent).toHaveBeenCalledWith("claude", expect.any(Object));
    });
  });

  it("renders multiple agent cards", async () => {
    mockGetAgents.mockResolvedValue([
      makeAgent({ agent_name: "claude", display_name: "Claude CLI" }),
      makeAgent({ id: 2, agent_name: "aider", display_name: "Aider" }),
      makeAgent({ id: 3, agent_name: "gemini", display_name: "Google Gemini CLI" }),
    ]);
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(await screen.findByText("Claude CLI")).toBeInTheDocument();
    expect(await screen.findByText("Aider")).toBeInTheDocument();
    expect(await screen.findByText("Google Gemini CLI")).toBeInTheDocument();
  });

  it("shows empty state when no agents", async () => {
    mockGetAgents.mockResolvedValue([]);
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(
      await screen.findByText("No agents configured. Start the backend to seed defaults."),
    ).toBeInTheDocument();
  });

  it("shows error state when API fails", async () => {
    mockGetAgents.mockRejectedValue(new Error("Network error"));
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(await screen.findByText(/Network error/)).toBeInTheDocument();
  });

  it("shows availability section after expanding", async () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(screen.getByText("Available on workspace servers")).toBeInTheDocument();
  });

  it("shows not found message when no availability", async () => {
    mockGetAgentAvailability.mockResolvedValue([]);
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(
      await screen.findByText("Not found on any workspace server"),
    ).toBeInTheDocument();
  });

  it("shows availability details when servers have agent", async () => {
    mockGetAgentAvailability.mockResolvedValue([
      { workspace_server_id: 1, version: "1.2.3", path: "/usr/local/bin/claude" },
    ]);
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    const header = await screen.findByText("Claude CLI");
    fireEvent.click(header.closest("button")!);
    expect(await screen.findByText("Server #1")).toBeInTheDocument();
    expect(await screen.findByText("v1.2.3")).toBeInTheDocument();
  });

  it("calls getAgents on mount", () => {
    render(<AgentSettingsPage />, { wrapper: Wrapper });
    expect(mockGetAgents).toHaveBeenCalledTimes(1);
  });
});