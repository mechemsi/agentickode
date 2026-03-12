// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ProjectInstructionsTab from "../components/settings/ProjectInstructionsTab";

vi.mock("../api", () => ({
  getInstructions: vi.fn().mockResolvedValue([]),
  getSecrets: vi.fn().mockResolvedValue([]),
  upsertGlobalInstruction: vi.fn().mockResolvedValue({}),
  upsertPhaseInstruction: vi.fn().mockResolvedValue({}),
  deleteInstruction: vi.fn().mockResolvedValue(undefined),
  getInstructionVersions: vi.fn().mockResolvedValue([]),
  createSecret: vi.fn().mockResolvedValue({}),
  updateSecret: vi.fn().mockResolvedValue({}),
  deleteSecret: vi.fn().mockResolvedValue(undefined),
  previewPrompt: vi.fn().mockResolvedValue({ system_prompt_section: "preview content", secrets_injected: ["API_KEY"] }),
}));

describe("ProjectInstructionsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders with empty state", async () => {
    render(<ProjectInstructionsTab projectId="test-proj" />);
    await waitFor(() => {
      expect(screen.getByText("Global Instructions")).toBeInTheDocument();
      expect(screen.getByText("Secrets")).toBeInTheDocument();
    });
  });

  it("renders with populated instructions", async () => {
    const { getInstructions, getSecrets } = await import("../api");
    (getInstructions as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { id: 1, project_id: "test-proj", phase_name: "__global__", content: "Global rules", is_active: true, created_at: "2026-01-01", updated_at: "2026-01-01" },
    ]);
    (getSecrets as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { id: 1, project_id: "test-proj", name: "API_KEY", inject_as: "env_var", phase_scope: null, created_at: "2026-01-01", updated_at: "2026-01-01" },
    ]);

    render(<ProjectInstructionsTab projectId="test-proj" />);
    await waitFor(() => {
      expect(screen.getByDisplayValue("Global rules")).toBeInTheDocument();
      expect(screen.getByText("API_KEY")).toBeInTheDocument();
      expect(screen.getByText("***")).toBeInTheDocument();
    });
  });

  it("shows save button for global instructions", async () => {
    render(<ProjectInstructionsTab projectId="test-proj" />);
    await waitFor(() => {
      expect(screen.getByText("Save Global")).toBeInTheDocument();
    });
  });

  it("loads prompt preview", async () => {
    render(<ProjectInstructionsTab projectId="test-proj" />);
    await waitFor(() => {
      expect(screen.getByText("Preview")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByText("Preview"));

    await waitFor(() => {
      expect(screen.getByText("preview content")).toBeInTheDocument();
      expect(screen.getByText(/API_KEY/)).toBeInTheDocument();
    });
  });

  it("shows version history toggle", async () => {
    render(<ProjectInstructionsTab projectId="test-proj" />);
    await waitFor(() => {
      expect(screen.getByText(/Version History/)).toBeInTheDocument();
    });
  });
});