// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetProjectsByServer = vi.fn();

vi.mock("../api", () => ({
  getProjectsByServer: (...args: unknown[]) => mockGetProjectsByServer(...args),
}));

import ProjectsPanel from "../components/servers/ProjectsPanel";

const sampleProject = {
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
  workspace_path: null as string | null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

const sampleServer = {
  id: 1,
  name: "dev-box",
  hostname: "10.0.0.5",
  port: 22,
  username: "root",
  ssh_key_path: null,
  workspace_root: "/workspace",
  status: "online",
  last_seen_at: null,
  error_message: null,
  worker_user: "coder",
  worker_user_status: null,
  worker_user_password: null,
  setup_log: null,
  agent_count: 2,
  project_count: 1,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

describe("ProjectsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    mockGetProjectsByServer.mockReturnValue(new Promise(() => {}));
    render(<ProjectsPanel serverId={1} />);
    expect(screen.getByText("Loading projects...")).toBeInTheDocument();
  });

  it("renders projects when loaded", async () => {
    mockGetProjectsByServer.mockResolvedValue([sampleProject]);

    render(<ProjectsPanel serverId={1} />);

    expect(await screen.findByText("my-project")).toBeInTheDocument();
    expect(screen.getByText("org/repo")).toBeInTheDocument();
  });

  it("shows empty state when no projects", async () => {
    mockGetProjectsByServer.mockResolvedValue([]);

    render(<ProjectsPanel serverId={1} />);

    expect(await screen.findByText("No projects linked to this server.")).toBeInTheDocument();
  });

  it("shows error on failure", async () => {
    mockGetProjectsByServer.mockRejectedValue(new Error("Network error"));

    render(<ProjectsPanel serverId={1} />);

    expect(await screen.findByText("Failed to load projects")).toBeInTheDocument();
  });

  it("calls API with correct serverId", async () => {
    mockGetProjectsByServer.mockResolvedValue([]);

    render(<ProjectsPanel serverId={42} />);

    await waitFor(() => {
      expect(mockGetProjectsByServer).toHaveBeenCalledWith(42);
    });
  });

  it("refresh button reloads data", async () => {
    mockGetProjectsByServer.mockResolvedValue([]);

    render(<ProjectsPanel serverId={1} />);

    await screen.findByText("No projects linked to this server.");

    mockGetProjectsByServer.mockResolvedValue([
      { ...sampleProject, project_id: "proj-new", project_slug: "new-project" },
    ]);

    fireEvent.click(screen.getByText("Refresh"));

    expect(await screen.findByText("new-project")).toBeInTheDocument();
  });

  it("shows VS Code link when project has workspace_path and server is provided", async () => {
    const projectWithPath = { ...sampleProject, workspace_path: "/workspace/myapp" };
    mockGetProjectsByServer.mockResolvedValue([projectWithPath]);

    render(<ProjectsPanel serverId={1} server={sampleServer} />);

    const link = await screen.findByTitle("Open in VS Code (requires Remote-SSH extension)");
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute(
      "href",
      "vscode://vscode-remote/ssh-remote+coder@10.0.0.5/workspace/myapp",
    );
  });

  it("does not show VS Code link when workspace_path is null", async () => {
    mockGetProjectsByServer.mockResolvedValue([sampleProject]);

    render(<ProjectsPanel serverId={1} server={sampleServer} />);

    await screen.findByText("my-project");
    expect(
      screen.queryByTitle("Open in VS Code (requires Remote-SSH extension)"),
    ).not.toBeInTheDocument();
  });

  it("does not show VS Code link when server is not provided", async () => {
    const projectWithPath = { ...sampleProject, workspace_path: "/workspace/myapp" };
    mockGetProjectsByServer.mockResolvedValue([projectWithPath]);

    render(<ProjectsPanel serverId={1} />);

    await screen.findByText("my-project");
    expect(
      screen.queryByTitle("Open in VS Code (requires Remote-SSH extension)"),
    ).not.toBeInTheDocument();
  });

  it("shows SSH config warning when server port is not 22", async () => {
    const projectWithPath = { ...sampleProject, workspace_path: "/workspace/myapp" };
    const nonStandardPortServer = { ...sampleServer, port: 2222 };
    mockGetProjectsByServer.mockResolvedValue([projectWithPath]);

    render(<ProjectsPanel serverId={1} server={nonStandardPortServer} />);

    await screen.findByText("my-project");
    expect(screen.getByText("SSH config needed")).toBeInTheDocument();
  });

  it("does not show SSH config warning when server port is 22", async () => {
    const projectWithPath = { ...sampleProject, workspace_path: "/workspace/myapp" };
    mockGetProjectsByServer.mockResolvedValue([projectWithPath]);

    render(<ProjectsPanel serverId={1} server={sampleServer} />);

    await screen.findByText("my-project");
    expect(screen.queryByText("SSH config needed")).not.toBeInTheDocument();
  });

  it("shows JetBrains button that opens IDE picker on click", async () => {
    const projectWithPath = { ...sampleProject, workspace_path: "/workspace/myapp" };
    mockGetProjectsByServer.mockResolvedValue([projectWithPath]);

    render(<ProjectsPanel serverId={1} server={sampleServer} />);

    const btn = await screen.findByTitle("Open in JetBrains Gateway");
    expect(btn).toBeInTheDocument();

    fireEvent.click(btn);
    expect(screen.getByText("Open with...")).toBeInTheDocument();
    expect(screen.getByText("IntelliJ IDEA")).toBeInTheDocument();
    expect(screen.getByText("PyCharm")).toBeInTheDocument();
    expect(screen.getByText("WebStorm")).toBeInTheDocument();
  });
});