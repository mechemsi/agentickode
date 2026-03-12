// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConfirmProvider } from "../components/shared/ConfirmDialog";
import { ToastProvider } from "../components/shared/Toast";
import WorkspaceServers from "../pages/WorkspaceServers";

const mockGetWorkspaceServers = vi.fn().mockResolvedValue([
  {
    id: 1,
    name: "coding-01",
    hostname: "10.10.50.25",
    port: 22,
    username: "root",
    ssh_key_path: null,
    workspace_root: "/workspaces",
    status: "online",
    last_seen_at: null,
    error_message: null,
    agent_count: 3,
    project_count: 5,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
]);
const mockCreateWorkspaceServer = vi.fn();
const mockUpdateWorkspaceServer = vi.fn();
const mockDeleteWorkspaceServer = vi.fn();
const mockTestWorkspaceServer = vi.fn();
const mockScanWorkspaceServer = vi.fn();
const mockDeployKeyToServer = vi.fn();
const mockCheckGitAccess = vi.fn();
const mockGenerateGitKey = vi.fn();
const mockGetAgentStatus = vi.fn();
const mockInstallAgent = vi.fn();
const mockGetProjectsByServer = vi.fn();

vi.mock("../api", () => ({
  getWorkspaceServers: (...args: unknown[]) => mockGetWorkspaceServers(...args),
  createWorkspaceServer: (...args: unknown[]) => mockCreateWorkspaceServer(...args),
  updateWorkspaceServer: (...args: unknown[]) => mockUpdateWorkspaceServer(...args),
  deleteWorkspaceServer: (...args: unknown[]) => mockDeleteWorkspaceServer(...args),
  testWorkspaceServer: (...args: unknown[]) => mockTestWorkspaceServer(...args),
  scanWorkspaceServer: (...args: unknown[]) => mockScanWorkspaceServer(...args),
  deployKeyToServer: (...args: unknown[]) => mockDeployKeyToServer(...args),
  checkGitAccess: (...args: unknown[]) => mockCheckGitAccess(...args),
  generateGitKey: (...args: unknown[]) => mockGenerateGitKey(...args),
  getAgentStatus: (...args: unknown[]) => mockGetAgentStatus(...args),
  installAgent: (...args: unknown[]) => mockInstallAgent(...args),
  getProjectsByServer: (...args: unknown[]) => mockGetProjectsByServer(...args),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <ConfirmProvider>
        <ToastProvider>{children}</ToastProvider>
      </ConfirmProvider>
    </MemoryRouter>
  );
}

describe("WorkspaceServers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWorkspaceServers.mockResolvedValue([
      {
        id: 1,
        name: "coding-01",
        hostname: "10.10.50.25",
        port: 22,
        username: "root",
        ssh_key_path: null,
        workspace_root: "/workspaces",
        status: "online",
        last_seen_at: null,
        error_message: null,
        agent_count: 3,
        project_count: 5,
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z",
      },
    ]);
  });

  it("renders heading", async () => {
    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(screen.getByText("Workspace Servers")).toBeInTheDocument();
  });

  it("renders add server button", () => {
    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(screen.getByText("Add Server")).toBeInTheDocument();
  });

  it("renders server list", async () => {
    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();
    expect(screen.getByText("10.10.50.25:22")).toBeInTheDocument();
    expect(screen.getByText("3 agents · 5 projects")).toBeInTheDocument();
  });

  it("clicking Add Server shows the form", async () => {
    render(<WorkspaceServers />, { wrapper: Wrapper });
    fireEvent.click(screen.getByText("Add Server"));
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getAllByText("Cancel").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByPlaceholderText("10.10.50.25")).toBeInTheDocument();
  });

  it("clicking Delete shows confirm dialog and deletes on confirm", async () => {
    mockDeleteWorkspaceServer.mockResolvedValue(undefined);

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Delete"));

    // Confirm dialog should appear
    expect(await screen.findByText("Delete Server")).toBeInTheDocument();
    expect(screen.getByText(/Delete this workspace server/)).toBeInTheDocument();

    // Click the confirm button in the dialog
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(mockDeleteWorkspaceServer).toHaveBeenCalledWith(1);
    });
  });

  it("clicking Delete does nothing when confirm cancelled", async () => {
    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Delete"));

    // Confirm dialog should appear
    expect(await screen.findByText("Delete Server")).toBeInTheDocument();

    // Click Cancel in the dialog
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(mockDeleteWorkspaceServer).not.toHaveBeenCalled();
  });

  it("clicking Test calls testWorkspaceServer and shows success toast", async () => {
    mockTestWorkspaceServer.mockResolvedValue({
      success: true,
      latency_ms: 12,
      error: null,
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Test"));

    await waitFor(() => {
      expect(mockTestWorkspaceServer).toHaveBeenCalledWith(1);
    });
    // Toast should appear
    expect(await screen.findByText("SSH OK (12ms)")).toBeInTheDocument();
  });

  it("clicking Test shows error toast on failure", async () => {
    mockTestWorkspaceServer.mockResolvedValue({
      success: false,
      latency_ms: null,
      error: "Connection refused",
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Test"));

    expect(await screen.findByText("SSH failed: Connection refused")).toBeInTheDocument();
  });

  it("clicking Scan calls scanWorkspaceServer and shows result toast", async () => {
    mockScanWorkspaceServer.mockResolvedValue({
      agents_found: 4,
      projects_found: 2,
      projects_imported: 1,
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Scan"));

    await waitFor(() => {
      expect(mockScanWorkspaceServer).toHaveBeenCalledWith(1);
    });
    expect(
      await screen.findByText("Found 4 agents, 2 projects (1 imported)"),
    ).toBeInTheDocument();
  });

  it("clicking Agents expands agent management panel", async () => {
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
        {
          agent_name: "aider",
          display_name: "Aider",
          description: "AI pair programming in the terminal",
          agent_type: "cli_binary",
          installed: false,
          version: null,
          path: null,
        },
      ],
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Agents"));

    await waitFor(() => {
      expect(mockGetAgentStatus).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("Aider")).toBeInTheDocument();
    expect(screen.getByText("Collapse")).toBeInTheDocument();
  });

  it("clicking Collapse hides agent management panel", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [
        {
          agent_name: "claude",
          display_name: "Claude Code",
          description: "Anthropic's AI coding agent",
          agent_type: "cli_binary",
          installed: true,
          version: null,
          path: null,
        },
      ],
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Agents"));
    expect(await screen.findByText("Claude Code")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Collapse"));
    await waitFor(() => {
      expect(screen.getByText("Agents")).toBeInTheDocument();
    });
  });

  it("shows Install button for missing agents", async () => {
    mockGetAgentStatus.mockResolvedValue({
      agents: [
        {
          agent_name: "claude",
          display_name: "Claude Code",
          description: "Anthropic's AI coding agent",
          agent_type: "cli_binary",
          installed: false,
          version: null,
          path: null,
        },
      ],
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Agents"));

    expect(await screen.findByText("Not Installed")).toBeInTheDocument();
    expect(screen.getByText("Install")).toBeInTheDocument();
  });

  it("displays error_message when present", async () => {
    mockGetWorkspaceServers.mockResolvedValue([
      {
        id: 1,
        name: "coding-01",
        hostname: "10.10.50.25",
        port: 22,
        username: "root",
        ssh_key_path: null,
        workspace_root: "/workspaces",
        status: "error",
        last_seen_at: null,
        error_message: "SSH connection timeout",
        agent_count: 0,
        project_count: 0,
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z",
      },
    ]);

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("SSH connection timeout")).toBeInTheDocument();
  });

  it("shows empty state when no servers exist", async () => {
    mockGetWorkspaceServers.mockResolvedValue([]);

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("No workspace servers configured yet.")).toBeInTheDocument();
  });

  it("shows deploy key prompt when SSH test fails", async () => {
    mockTestWorkspaceServer.mockResolvedValue({
      success: false,
      latency_ms: null,
      error: "Permission denied",
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Test"));

    expect(await screen.findByPlaceholderText("Server password")).toBeInTheDocument();
    expect(screen.getByText("Deploy Key")).toBeInTheDocument();
  });

  it("calls deployKeyToServer when Deploy Key is clicked", async () => {
    mockTestWorkspaceServer.mockResolvedValue({
      success: false,
      latency_ms: null,
      error: "Permission denied",
    });
    mockDeployKeyToServer.mockResolvedValue({
      success: true,
      latency_ms: 10,
      error: null,
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Test"));
    expect(await screen.findByPlaceholderText("Server password")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Server password"), {
      target: { value: "mypassword" },
    });
    fireEvent.click(screen.getByText("Deploy Key"));

    await waitFor(() => {
      expect(mockDeployKeyToServer).toHaveBeenCalledWith(1, "mypassword");
    });
    expect(await screen.findByText("SSH key deployed successfully")).toBeInTheDocument();
  });

  it("hides deploy key prompt on cancel", async () => {
    mockTestWorkspaceServer.mockResolvedValue({
      success: false,
      latency_ms: null,
      error: "Permission denied",
    });

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Test"));
    expect(await screen.findByPlaceholderText("Server password")).toBeInTheDocument();

    // Find the Cancel button in the deploy key section (not the form cancel)
    const cancelButtons = screen.getAllByText("Cancel");
    fireEvent.click(cancelButtons[cancelButtons.length - 1]);

    await waitFor(() => {
      expect(screen.queryByPlaceholderText("Server password")).not.toBeInTheDocument();
    });
  });

  it("clicking Projects expands projects panel", async () => {
    mockGetProjectsByServer.mockResolvedValue([
      {
        project_id: "proj-1",
        project_slug: "my-project",
        repo_owner: "org",
        repo_name: "repo",
        default_branch: "main",
        task_source: "github",
        git_provider: "github",
        workspace_config: null,
        ai_config: null,
        workspace_server_id: 1,
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z",
      },
    ]);

    render(<WorkspaceServers />, { wrapper: Wrapper });
    expect(await screen.findByText("coding-01")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Projects"));

    await waitFor(() => {
      expect(mockGetProjectsByServer).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText("my-project")).toBeInTheDocument();
  });
});