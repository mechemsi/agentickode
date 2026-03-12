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
  workspace_server_id: null,
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

  it("shows workspace_server dropdown always (with or without servers)", () => {
    render(<ProjectForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText("Workspace Server (used to verify repo access)")).toBeInTheDocument();
  });

  it("shows server options when servers prop provided", () => {
    render(<ProjectForm onSubmit={vi.fn()} onCancel={vi.fn()} servers={mockServers} />);
    expect(screen.getByText("-- none (direct API) --")).toBeInTheDocument();
    expect(screen.getByText("coding-01")).toBeInTheDocument();
    expect(screen.getByText("coding-02")).toBeInTheDocument();
  });

  it("includes workspace_server_id in onSubmit data when server selected (edit mode)", () => {
    const onSubmit = vi.fn();
    render(
      <ProjectForm
        initial={editInitial}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        servers={mockServers}
      />,
    );

    // Find the server select (the one containing coding-01)
    const allSelects = screen.getAllByRole("combobox");
    const serverSelect = allSelects.find((s) => s.querySelector('option[value="1"]'));
    fireEvent.change(serverSelect!, { target: { value: "1" } });

    fireEvent.click(screen.getByText("Save"));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ workspace_server_id: 1 }),
    );
  });

  it("sends workspace_server_id as null when none selected (edit mode)", () => {
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
      expect.objectContaining({ workspace_server_id: null }),
    );
  });
});