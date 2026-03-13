// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("../api", () => ({
  getProjects: vi.fn().mockResolvedValue([
    {
      project_id: "proj-1",
      project_slug: "my-project",
      repo_owner: "org",
      repo_name: "repo",
      default_branch: "main",
      task_source: "plane",
      git_provider: "gitea",
      workspace_config: null,
      ai_config: null,
      workspace_server_id: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    },
  ]),
  getWorkflowTemplates: vi.fn().mockResolvedValue([
    {
      id: 1,
      name: "Default Template",
      description: "",
      label_rules: [],
      phases: [],
      is_default: true,
      is_system: false,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    },
  ]),
  getWorkspaceServers: vi.fn().mockResolvedValue([
    {
      id: 1,
      name: "dev-server",
      hostname: "10.0.0.1",
      port: 22,
      username: "root",
      ssh_key_path: null,
      workspace_root: "/workspaces",
      status: "online",
      last_seen_at: null,
      error_message: null,
      worker_user: "coder",
      worker_user_status: "ready",
      worker_user_password: null,
      setup_log: null,
      agent_count: 1,
      project_count: 2,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    },
  ]),
  getProjectIssues: vi.fn().mockResolvedValue([]),
  createRun: vi.fn(),
}));

// Mock Toast
vi.mock("../components/shared/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));

import * as api from "../api";
import NewRun from "../pages/NewRun";

function renderNewRun() {
  return render(
    <MemoryRouter initialEntries={["/runs/new"]}>
      <Routes>
        <Route path="/runs/new" element={<NewRun />} />
        <Route path="/runs/:id" element={<div>Run Detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("NewRun", () => {
  it("renders the page heading", () => {
    renderNewRun();
    expect(screen.getByText("New Run")).toBeInTheDocument();
  });

  it("renders required form fields", () => {
    renderNewRun();
    expect(screen.getByText(/Project/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Fix the login form/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Describe what needs/i)).toBeInTheDocument();
  });

  it("renders create run button", () => {
    renderNewRun();
    expect(screen.getByRole("button", { name: /Create Run/i })).toBeInTheDocument();
  });

  it("renders cancel button", () => {
    renderNewRun();
    expect(screen.getByRole("button", { name: /Cancel/i })).toBeInTheDocument();
  });

  it("loads project options", async () => {
    renderNewRun();
    await waitFor(() => {
      expect(screen.getByText(/my-project/)).toBeInTheDocument();
    });
  });

  it("shows validation errors when submitting empty form", async () => {
    renderNewRun();
    fireEvent.click(screen.getByRole("button", { name: /Create Run/i }));
    await waitFor(() => {
      expect(screen.getByText("Project is required")).toBeInTheDocument();
      expect(screen.getByText("Title is required")).toBeInTheDocument();
    });
  });

  it("calls createRun with correct data on submit", async () => {
    vi.mocked(api.createRun).mockResolvedValueOnce({
      id: 42,
      status: "pending",
      title: "Fix bug",
      project_id: "proj-1",
      branch_name: "agentickode/my-project/123456",
    });

    renderNewRun();

    // Wait for projects to load
    await waitFor(() => {
      expect(screen.getByText(/my-project/)).toBeInTheDocument();
    });

    // Select project
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "proj-1" } });

    // Fill title
    fireEvent.change(screen.getByPlaceholderText(/Fix the login form/i), {
      target: { value: "Fix bug" },
    });

    // Submit
    fireEvent.click(screen.getByRole("button", { name: /Create Run/i }));

    await waitFor(() => {
      expect(api.createRun).toHaveBeenCalledWith(
        expect.objectContaining({
          project_id: "proj-1",
          title: "Fix bug",
        }),
      );
    });
  });

  it("navigates to run detail on successful creation", async () => {
    vi.mocked(api.createRun).mockResolvedValueOnce({
      id: 99,
      status: "pending",
      title: "My run",
      project_id: "proj-1",
      branch_name: "agentickode/my-project/999",
    });

    renderNewRun();

    await waitFor(() => {
      expect(screen.getByText(/my-project/)).toBeInTheDocument();
    });

    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "proj-1" } });
    fireEvent.change(screen.getByPlaceholderText(/Fix the login form/i), {
      target: { value: "My run" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Create Run/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/runs/99");
    });
  });

  it("shows advanced options when toggle is clicked", async () => {
    renderNewRun();
    fireEvent.click(screen.getByText("Advanced Options"));
    expect(screen.getByText("Per-Phase Agent Overrides")).toBeInTheDocument();
    expect(screen.getByText("coding")).toBeInTheDocument();
    expect(screen.getByText("reviewing")).toBeInTheDocument();
  });

  it("fetches issues when project is selected and shows picker", async () => {
    vi.mocked(api.getProjectIssues).mockResolvedValueOnce([
      {
        number: 10,
        title: "Fix login bug",
        body: "Login form crashes on submit",
        labels: ["bug"],
        url: "https://gitea.test/org/repo/issues/10",
        state: "open",
      },
    ]);

    renderNewRun();

    await waitFor(() => {
      expect(screen.getByText(/my-project/)).toBeInTheDocument();
    });

    // Select project to trigger issue fetch
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "proj-1" } });

    await waitFor(() => {
      expect(api.getProjectIssues).toHaveBeenCalledWith("proj-1");
    });

    // Issue picker should appear with the fetched issue
    await waitFor(() => {
      expect(screen.getByText(/Fix login bug/)).toBeInTheDocument();
    });
  });

  it("auto-fills title and description when issue is selected", async () => {
    vi.mocked(api.getProjectIssues).mockResolvedValueOnce([
      {
        number: 7,
        title: "Add dark mode",
        body: "Implement dark mode toggle in settings",
        labels: [],
        url: "https://gitea.test/org/repo/issues/7",
        state: "open",
      },
    ]);

    renderNewRun();

    await waitFor(() => {
      expect(screen.getByText(/my-project/)).toBeInTheDocument();
    });

    // Select project
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "proj-1" } });

    // Wait for issues to load
    await waitFor(() => {
      expect(screen.getByText(/Add dark mode/)).toBeInTheDocument();
    });

    // Select the issue from the picker
    const issueSelect = screen.getByDisplayValue("-- Type manually --");
    fireEvent.change(issueSelect, { target: { value: "7" } });

    // Title and description should be auto-filled
    const titleInput = screen.getByPlaceholderText(/Fix the login form/i) as HTMLInputElement;
    expect(titleInput.value).toBe("Add dark mode");

    const descInput = screen.getByPlaceholderText(/Describe what needs/i) as HTMLInputElement;
    expect(descInput.value).toBe("Implement dark mode toggle in settings");
  });

  it("renders skip schedule checkbox and includes it in createRun", async () => {
    vi.mocked(api.createRun).mockResolvedValueOnce({
      id: 55,
      status: "pending",
      title: "Urgent fix",
      project_id: "proj-1",
      branch_name: "agentickode/my-project/555",
    });

    renderNewRun();

    await waitFor(() => {
      expect(screen.getByText(/my-project/)).toBeInTheDocument();
    });

    // The skip schedule checkbox should be visible
    expect(screen.getByText("Skip schedule")).toBeInTheDocument();

    // Select project and fill title
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "proj-1" } });
    fireEvent.change(screen.getByPlaceholderText(/Fix the login form/i), {
      target: { value: "Urgent fix" },
    });

    // Check the skip schedule checkbox
    const checkbox = screen.getByRole("checkbox", { name: /skip schedule/i });
    fireEvent.click(checkbox);

    // Submit
    fireEvent.click(screen.getByRole("button", { name: /Create Run/i }));

    await waitFor(() => {
      expect(api.createRun).toHaveBeenCalledWith(
        expect.objectContaining({
          project_id: "proj-1",
          title: "Urgent fix",
          skip_schedule: true,
        }),
      );
    });
  });
});