// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetAgentStatus = vi.fn();
const mockInstallAgentStream = vi.fn();

vi.mock("../api", () => ({
  getAgentStatus: (...args: unknown[]) => mockGetAgentStatus(...args),
  installAgentStream: (...args: unknown[]) => mockInstallAgentStream(...args),
}));

import AgentManagementPanel from "../components/servers/AgentManagementPanel";

describe("AgentManagementPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    mockGetAgentStatus.mockReturnValue(new Promise(() => {}));
    render(<AgentManagementPanel serverId={1} />);
    expect(screen.getByText("Checking agents...")).toBeInTheDocument();
  });

  it("renders agents from by_user (worker only)", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [],
      by_user: [
        {
          user: "coder",
          agents: [
            {
              agent_name: "claude",
              display_name: "Claude Code",
              description: "Anthropic's AI coding agent",
              agent_type: "cli_binary",
              installed: true,
              version: "1.0.0",
              path: "/home/coder/.local/bin/claude",
            },
            {
              agent_name: "aider",
              display_name: "Aider",
              description: "AI pair programming",
              agent_type: "cli_binary",
              installed: false,
              version: null,
              path: null,
            },
          ],
        },
      ],
    });

    render(<AgentManagementPanel serverId={1} />);

    expect(await screen.findByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("Aider")).toBeInTheDocument();
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
  });

  it("renders flat agents list as fallback", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [
        {
          agent_name: "claude",
          display_name: "Claude Code",
          description: "Anthropic's AI coding agent",
          agent_type: "cli_binary",
          installed: true,
          version: "1.0.0",
          path: "/usr/bin/claude",
        },
      ],
      by_user: [],
    });

    render(<AgentManagementPanel serverId={1} />);

    expect(await screen.findByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
  });

  it("shows Install button for missing agents", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [
        {
          agent_name: "codex",
          display_name: "Codex CLI",
          description: "OpenAI's coding agent",
          agent_type: "cli_binary",
          installed: false,
          version: null,
          path: null,
        },
      ],
      by_user: [],
    });

    render(<AgentManagementPanel serverId={1} />);

    expect(await screen.findByText("Not Installed")).toBeInTheDocument();
    expect(screen.getByText("Install")).toBeInTheDocument();
  });

  it("shows Installed badge for installed agents", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [
        {
          agent_name: "claude",
          display_name: "Claude Code",
          description: "Anthropic's AI coding agent",
          agent_type: "cli_binary",
          installed: true,
          version: "1.0.0",
          path: "/usr/bin/claude",
        },
      ],
      by_user: [],
    });

    render(<AgentManagementPanel serverId={1} />);

    expect(await screen.findByText("Installed")).toBeInTheDocument();
  });

  it("calls installAgentStream on Install click and shows dialog", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [],
      by_user: [
        {
          user: "coder",
          agents: [
            {
              agent_name: "aider",
              display_name: "Aider",
              description: "AI pair programming",
              agent_type: "cli_binary",
              installed: false,
              version: null,
              path: null,
            },
          ],
        },
      ],
    });
    mockInstallAgentStream.mockImplementation(async (_serverId: number, _agentName: string, onLine: (line: string, type: string) => void) => {
      onLine("Installing aider...", "output");
      onLine("Done", "complete");
    });

    render(<AgentManagementPanel serverId={1} />);

    expect(await screen.findByText("Install")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Install"));

    await waitFor(() => {
      expect(mockInstallAgentStream).toHaveBeenCalledWith(1, "aider", expect.any(Function));
    });
  });

  it("shows error dialog when install fails", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [
        {
          agent_name: "codex",
          display_name: "Codex CLI",
          description: "OpenAI's coding agent",
          agent_type: "cli_binary",
          installed: false,
          version: null,
          path: null,
        },
      ],
      by_user: [],
    });
    mockInstallAgentStream.mockImplementation(async (_serverId: number, _agentName: string, onLine: (line: string, type: string) => void) => {
      onLine("Prerequisite not found: npm", "error");
    });

    render(<AgentManagementPanel serverId={1} />);

    expect(await screen.findByText("Install")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Install"));

    expect(await screen.findByText("Prerequisite not found: npm")).toBeInTheDocument();
  });

  it("does not show SSH user / worker user labels", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [],
      by_user: [
        {
          user: "coder",
          agents: [
            {
              agent_name: "claude",
              display_name: "Claude Code",
              description: "Anthropic's AI coding agent",
              agent_type: "cli_binary",
              installed: true,
              version: "1.0.0",
              path: "/home/coder/.local/bin/claude",
            },
          ],
        },
      ],
    });

    render(<AgentManagementPanel serverId={1} />);

    await screen.findByText("Claude Code");
    expect(screen.queryByText("(SSH user)")).not.toBeInTheDocument();
    expect(screen.queryByText("(worker user)")).not.toBeInTheDocument();
  });
});