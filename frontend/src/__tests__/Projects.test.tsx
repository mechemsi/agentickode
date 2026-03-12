// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getProjects: vi.fn().mockResolvedValue([
    {
      project_id: "p1", project_slug: "my-project", repo_owner: "org",
      repo_name: "repo", default_branch: "main", task_source: "plane",
      git_provider: "gitea", workspace_config: null, ai_config: null,
      workspace_server_id: null,
      created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z",
    },
  ]),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  getWorkspaceServers: vi.fn().mockResolvedValue([]),
}));

import Projects from "../pages/Projects";

describe("Projects", () => {
  it("renders the heading", async () => {
    render(<MemoryRouter><Projects /></MemoryRouter>);
    expect(screen.getByText("Projects")).toBeInTheDocument();
  });

  it("renders add button", () => {
    render(<MemoryRouter><Projects /></MemoryRouter>);
    expect(screen.getByText("Add Project")).toBeInTheDocument();
  });

  it("renders project list", async () => {
    render(<MemoryRouter><Projects /></MemoryRouter>);
    expect(await screen.findByText("my-project")).toBeInTheDocument();
  });
});