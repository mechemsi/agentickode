// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ProjectForm from "../components/shared/ProjectForm";
import type { WorkspaceServer } from "../types";

const mockServers: WorkspaceServer[] = [
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
    worker_user: null,
    worker_user_status: null,
    worker_user_password: null,
    setup_log: null,
    agent_count: 3,
    project_count: 5,
    server_group_id: null,
    server_group_name: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
  {
    id: 2,
    name: "coding-02",
    hostname: "10.10.50.26",
    port: 22,
    username: "root",
    ssh_key_path: null,
    workspace_root: "/workspaces",
    status: "online",
    last_seen_at: null,
    error_message: null,
    worker_user: null,
    worker_user_status: null,
    worker_user_password: null,
    setup_log: null,
    agent_count: 1,
    project_count: 2,
    server_group_id: null,
    server_group_name: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
];

const editInitial = {
  project_id: "p1",
  project_slug: "my-project",
  repo_owner: "org",
  repo_name: "repo",
  default_branch: "main",
  task_source: "plain",
  git_provider: "gitea",
  workspace_server_ids: [],
};

describe("ProjectForm", () => {
  it("renders git URL input and Save/Cancel buttons in create mode", () => {
    render(<ProjectForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByPlaceholderText("https://github.com/owner/repo")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("calls onCancel when cancel clicked", () => {
    const onCancel = vi.fn();
    render(<ProjectForm onSubmit={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("shows error when Save clicked in create mode without parsing", () => {
    const onSubmit = vi.fn();
    render(<ProjectForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("Save"));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Parse git URL first")).toBeInTheDocument();
  });

  it("calls onSubmit in edit mode without requiring parse", () => {
    const onSubmit = vi.fn();
    render(<ProjectForm initial={editInitial} onSubmit={onSubmit} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("Save"));
    expect(onSubmit).toHaveBeenCalled();
  });

  it("does not show git URL input in edit mode", () => {
    render(<ProjectForm initial={editInitial} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByPlaceholderText("https://github.com/owner/repo")).not.toBeInTheDocument();
  });

  it("populates initial values when editing", () => {
    render(<ProjectForm initial={editInitial} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByDisplayValue("my-project")).toBeInTheDocument();
    expect(screen.getByDisplayValue("org")).toBeInTheDocument();
  });

  it("create mode is minimal: advanced fields hidden until toggled", () => {
    render(<ProjectForm onSubmit={vi.fn()} onCancel={vi.fn()} servers={mockServers} />);
    // Minimal view: URL + project name + advanced toggle + Save
    expect(screen.getByPlaceholderText("https://github.com/owner/repo")).toBeInTheDocument();
    expect(screen.getByText("Project name / slug")).toBeInTheDocument();
    expect(screen.getByText("Advanced options")).toBeInTheDocument();
    // Advanced fields are NOT rendered yet
    expect(
      screen.queryByText("Workspace Servers (used to verify repo access)"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("coding-01")).not.toBeInTheDocument();
    expect(screen.queryByTestId("local-path-input")).not.toBeInTheDocument();
  });

  it("expanding Advanced reveals workspace servers + repo fields in create mode", () => {
    render(<ProjectForm onSubmit={vi.fn()} onCancel={vi.fn()} servers={mockServers} />);
    fireEvent.click(screen.getByTestId("toggle-advanced"));
    expect(
      screen.getByText("Workspace Servers (used to verify repo access)"),
    ).toBeInTheDocument();
    expect(screen.getByText("coding-01")).toBeInTheDocument();
    expect(screen.getByText("coding-02")).toBeInTheDocument();
    expect(screen.getByTestId("local-path-input")).toBeInTheDocument();
  });

  it("edit mode shows advanced fields without toggling", () => {
    render(
      <ProjectForm initial={editInitial} onSubmit={vi.fn()} onCancel={vi.fn()} servers={mockServers} />,
    );
    expect(
      screen.getByText("Workspace Servers (used to verify repo access)"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("local-path-input")).toBeInTheDocument();
  });

  it("includes workspace_server_ids in onSubmit data when server checked (edit mode)", () => {
    const onSubmit = vi.fn();
    render(
      <ProjectForm
        initial={editInitial}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        servers={mockServers}
      />,
    );

    // Check the first server checkbox
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);

    fireEvent.click(screen.getByText("Save"));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ workspace_server_ids: [1] }),
    );
  });

  it("sends workspace_server_ids as empty array when none checked (edit mode)", () => {
    const onSubmit = vi.fn();
    render(
      <ProjectForm
        initial={editInitial}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        servers={mockServers}
      />,
    );

    fireEvent.click(screen.getByText("Save"));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ workspace_server_ids: [] }),
    );
  });

  it("hides Notion fields when task_source is not notion", () => {
    const initialGithub = { ...editInitial, task_source: "github" };
    render(
      <ProjectForm initial={initialGithub} onSubmit={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByTestId("notion-fields")).not.toBeInTheDocument();
  });

  it("shows Notion fields when task_source is notion", () => {
    const initialNotion = { ...editInitial, task_source: "notion" };
    render(
      <ProjectForm initial={initialNotion} onSubmit={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByTestId("notion-fields")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("UUID of the database to watch")).toBeInTheDocument();
  });

  it("hides polling block for plain task_source", () => {
    const initialPlain = { ...editInitial, task_source: "plain" };
    render(
      <ProjectForm initial={initialPlain} onSubmit={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByTestId("polling-fields")).not.toBeInTheDocument();
  });

  it("shows polling block for poll-capable sources", () => {
    const initialGithub = { ...editInitial, task_source: "github" };
    render(<ProjectForm initial={initialGithub} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId("polling-fields")).toBeInTheDocument();
    expect(screen.getByText("Enable periodic issue polling")).toBeInTheDocument();
  });

  it("submits local_path and worker_user_override when filled", () => {
    const onSubmit = vi.fn();
    render(
      <ProjectForm initial={editInitial} onSubmit={onSubmit} onCancel={vi.fn()} />,
    );
    fireEvent.change(screen.getByTestId("local-path-input"), {
      target: { value: "/home/me/projects/myapp" },
    });
    fireEvent.change(screen.getByTestId("worker-user-override-input"), {
      target: { value: "developer" },
    });
    fireEvent.click(screen.getByText("Save"));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        local_path: "/home/me/projects/myapp",
        worker_user_override: "developer",
      }),
    );
  });

  it("submits null when local_path / worker_user_override are blank", () => {
    const onSubmit = vi.fn();
    render(
      <ProjectForm initial={editInitial} onSubmit={onSubmit} onCancel={vi.fn()} />,
    );
    fireEvent.click(screen.getByText("Save"));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        local_path: null,
        worker_user_override: null,
      }),
    );
  });

  it("submits integration_config when Notion fields are filled", () => {
    const onSubmit = vi.fn();
    const initialNotion = { ...editInitial, task_source: "notion" };
    render(
      <ProjectForm initial={initialNotion} onSubmit={onSubmit} onCancel={vi.fn()} />,
    );
    fireEvent.change(screen.getByPlaceholderText("UUID of the database to watch"), {
      target: { value: "db-abc" },
    });
    fireEvent.click(screen.getByText("Save"));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        integration_config: expect.objectContaining({ notion_database_id: "db-abc" }),
      }),
    );
  });

  it("surfaces the error when onSubmit rejects (no longer a silent fail)", async () => {
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        new Error("POST /projects: SSH repo verification failed: Permission denied (publickey)"),
      );
    render(<ProjectForm initial={editInitial} onSubmit={onSubmit} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("Save"));
    expect(
      await screen.findByText(/SSH repo verification failed: Permission denied/),
    ).toBeInTheDocument();
  });

  it("disables Save while the submission is in flight", async () => {
    let resolve: () => void = () => {};
    const onSubmit = vi.fn().mockReturnValue(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );
    render(<ProjectForm initial={editInitial} onSubmit={onSubmit} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText("Saving…")).toBeInTheDocument();
    resolve();
  });
});