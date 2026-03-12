// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ConfirmProvider } from "../components/shared/ConfirmDialog";
import { ToastProvider } from "../components/shared/Toast";
import RoleConfigs from "../pages/RoleConfigs";

// Mock all API calls
const mockGetRoleConfigs = vi.fn();
const mockGetPromptOverrides = vi.fn();
const mockUpsertPromptOverride = vi.fn();
const mockDeletePromptOverride = vi.fn();
const mockUpdateRoleConfig = vi.fn();
const mockCreateRoleConfig = vi.fn();
const mockDeleteRoleConfig = vi.fn();
const mockResetRoleConfig = vi.fn();
const mockGetRoleAssignments = vi.fn();
const mockUpdateRoleAssignments = vi.fn();
const mockDeleteRoleAssignment = vi.fn();
const mockGetOllamaServers = vi.fn();
const mockGetWorkspaceServers = vi.fn();

vi.mock("../api", () => ({
  getRoleConfigs: (...args: unknown[]) => mockGetRoleConfigs(...args),
  getPromptOverrides: (...args: unknown[]) => mockGetPromptOverrides(...args),
  upsertPromptOverride: (...args: unknown[]) => mockUpsertPromptOverride(...args),
  deletePromptOverride: (...args: unknown[]) => mockDeletePromptOverride(...args),
  updateRoleConfig: (...args: unknown[]) => mockUpdateRoleConfig(...args),
  createRoleConfig: (...args: unknown[]) => mockCreateRoleConfig(...args),
  deleteRoleConfig: (...args: unknown[]) => mockDeleteRoleConfig(...args),
  resetRoleConfig: (...args: unknown[]) => mockResetRoleConfig(...args),
  getRoleAssignments: (...args: unknown[]) => mockGetRoleAssignments(...args),
  updateRoleAssignments: (...args: unknown[]) => mockUpdateRoleAssignments(...args),
  deleteRoleAssignment: (...args: unknown[]) => mockDeleteRoleAssignment(...args),
  getOllamaServers: (...args: unknown[]) => mockGetOllamaServers(...args),
  getWorkspaceServers: (...args: unknown[]) => mockGetWorkspaceServers(...args),
}));

const sampleConfig = {
  id: 1,
  agent_name: "coder",
  display_name: "Coder",
  description: "Coding agent",
  system_prompt: "You are a coder",
  user_prompt_template: "Do: {title}",
  phase_binding: "coding",
  is_system: true,
  default_temperature: 0.3,
  default_num_predict: 2048,
  extra_params: {},
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

const sampleOverride = {
  id: 10,
  role_config_id: 1,
  cli_agent_name: "claude",
  system_prompt: "Custom system",
  user_prompt_template: "Custom template {title}",
  minimal_mode: false,
  extra_params: {},
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <ConfirmProvider>
        <ToastProvider>{children}</ToastProvider>
      </ConfirmProvider>
    </MemoryRouter>
  );
}

describe("RolePromptOverrides", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetRoleConfigs.mockResolvedValue([sampleConfig]);
    mockGetPromptOverrides.mockResolvedValue([]);
    mockGetRoleAssignments.mockResolvedValue([]);
    mockGetOllamaServers.mockResolvedValue([]);
    mockGetWorkspaceServers.mockResolvedValue([]);
  });

  it("renders the page heading", async () => {
    render(
      <Wrapper>
        <RoleConfigs />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText("Roles")).toBeInTheDocument();
    });
  });

  it("renders the overrides section header when config is expanded", async () => {
    render(
      <Wrapper>
        <RoleConfigs />
      </Wrapper>,
    );

    // Wait for configs to load
    await waitFor(() => screen.getByText("Coder"));

    // Expand the config card
    fireEvent.click(screen.getByText("Coder"));

    await waitFor(() => {
      expect(screen.getByText("Per-Agent Overrides")).toBeInTheDocument();
    });
  });

  it("lists all known CLI agents in the overrides section", async () => {
    render(
      <Wrapper>
        <RoleConfigs />
      </Wrapper>,
    );

    await waitFor(() => screen.getByText("Coder"));
    fireEvent.click(screen.getByText("Coder"));

    // Click to expand "Per-Agent Overrides"
    await waitFor(() => screen.getByText("Per-Agent Overrides"));
    fireEvent.click(screen.getByText("Per-Agent Overrides"));

    await waitFor(() => {
      for (const agent of ["claude", "codex", "gemini", "kimi", "aider", "opencode"]) {
        expect(screen.getByText(agent)).toBeInTheDocument();
      }
    });
  });

  it("shows override active badge when an override exists", async () => {
    mockGetPromptOverrides.mockResolvedValue([sampleOverride]);

    render(
      <Wrapper>
        <RoleConfigs />
      </Wrapper>,
    );

    await waitFor(() => screen.getByText("Coder"));
    fireEvent.click(screen.getByText("Coder"));

    await waitFor(() => screen.getByText("Per-Agent Overrides"));
    fireEvent.click(screen.getByText("Per-Agent Overrides"));

    await waitFor(() => {
      expect(screen.getByText("override active")).toBeInTheDocument();
    });
  });

  it("shows minimal badge when override has minimal_mode=true", async () => {
    mockGetPromptOverrides.mockResolvedValue([
      { ...sampleOverride, minimal_mode: true },
    ]);

    render(
      <Wrapper>
        <RoleConfigs />
      </Wrapper>,
    );

    await waitFor(() => screen.getByText("Coder"));
    fireEvent.click(screen.getByText("Coder"));

    await waitFor(() => screen.getByText("Per-Agent Overrides"));
    fireEvent.click(screen.getByText("Per-Agent Overrides"));

    await waitFor(() => {
      expect(screen.getByText("minimal")).toBeInTheDocument();
    });
  });

  it("expands an agent row and shows form fields", async () => {
    render(
      <Wrapper>
        <RoleConfigs />
      </Wrapper>,
    );

    await waitFor(() => screen.getByText("Coder"));
    fireEvent.click(screen.getByText("Coder"));

    await waitFor(() => screen.getByText("Per-Agent Overrides"));
    fireEvent.click(screen.getByText("Per-Agent Overrides"));

    await waitFor(() => screen.getByText("claude"));

    // Expand claude row
    fireEvent.click(screen.getByText("claude"));

    await waitFor(() => {
      expect(
        screen.getByText("Minimal mode — skip system prompt, send only the task instruction"),
      ).toBeInTheDocument();
      expect(screen.getAllByPlaceholderText("Leave empty to use default").length).toBeGreaterThan(0);
    });
  });

  it("calls upsertPromptOverride with correct args on save", async () => {
    mockUpsertPromptOverride.mockResolvedValue(sampleOverride);

    render(
      <Wrapper>
        <RoleConfigs />
      </Wrapper>,
    );

    await waitFor(() => screen.getByText("Coder"));
    fireEvent.click(screen.getByText("Coder"));

    await waitFor(() => screen.getByText("Per-Agent Overrides"));
    fireEvent.click(screen.getByText("Per-Agent Overrides"));

    await waitFor(() => screen.getByText("claude"));
    fireEvent.click(screen.getByText("claude"));

    await waitFor(() => screen.getAllByText("Save"));

    // Fill in the system prompt
    const textareas = screen.getAllByPlaceholderText("Leave empty to use default");
    fireEvent.change(textareas[0], { target: { value: "My custom system" } });

    // Click Save button for this agent row
    const saveButtons = screen.getAllByText("Save");
    fireEvent.click(saveButtons[0]);

    await waitFor(() => {
      expect(mockUpsertPromptOverride).toHaveBeenCalledWith(
        "coder",
        "claude",
        expect.objectContaining({
          system_prompt: "My custom system",
          minimal_mode: false,
        }),
      );
    });
  });

  it("calls deletePromptOverride when Remove override is clicked", async () => {
    mockGetPromptOverrides.mockResolvedValue([sampleOverride]);
    mockDeletePromptOverride.mockResolvedValue(undefined);
    // After delete, return empty
    mockGetPromptOverrides.mockResolvedValueOnce([sampleOverride]).mockResolvedValue([]);

    render(
      <Wrapper>
        <RoleConfigs />
      </Wrapper>,
    );

    await waitFor(() => screen.getByText("Coder"));
    fireEvent.click(screen.getByText("Coder"));

    await waitFor(() => screen.getByText("Per-Agent Overrides"));
    fireEvent.click(screen.getByText("Per-Agent Overrides"));

    await waitFor(() => screen.getByText("claude"));

    // Expand claude row
    fireEvent.click(screen.getByText("claude"));

    await waitFor(() => screen.getByText("Remove override"));

    fireEvent.click(screen.getByText("Remove override"));

    await waitFor(() => {
      expect(mockDeletePromptOverride).toHaveBeenCalledWith("coder", "claude");
    });
  });
});