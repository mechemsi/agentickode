// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ComparisonResultsPanel from "../components/runs/ComparisonResultsPanel";
import type { ComparisonResults } from "../types";

vi.mock("../api", () => ({
  pickComparisonWinner: vi.fn().mockResolvedValue({ status: "winner_picked" }),
}));

const baseComparison: ComparisonResults = {
  comparison_mode: true,
  base_commit: "abc123def456",
  agents: {
    a: {
      agent_name: "claude",
      branch: "compare-claude-1",
      results: [
        { subtask_title: "Implement feature", files_changed: ["src/a.ts"], exit_code: 0 },
      ],
      total_cost_usd: 0.033,
      total_duration_seconds: 120.5,
      invocation_ids: [1],
    },
    b: {
      agent_name: "codex",
      branch: "compare-codex-1",
      results: [
        { subtask_title: "Implement feature", files_changed: ["src/b.ts"], exit_code: 0 },
      ],
      total_cost_usd: 0.009,
      total_duration_seconds: 85.2,
      invocation_ids: [2],
    },
  },
  winner: null,
};

describe("ComparisonResultsPanel", () => {
  const onWinnerPicked = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders two agent columns", () => {
    render(
      <ComparisonResultsPanel runId={1} comparison={baseComparison} onWinnerPicked={onWinnerPicked} />,
    );
    expect(screen.getByText("claude")).toBeInTheDocument();
    expect(screen.getByText("codex")).toBeInTheDocument();
    expect(screen.getByText("Agent A")).toBeInTheDocument();
    expect(screen.getByText("Agent B")).toBeInTheDocument();
  });

  it("shows pick winner buttons when no winner", () => {
    render(
      <ComparisonResultsPanel runId={1} comparison={baseComparison} onWinnerPicked={onWinnerPicked} />,
    );
    expect(screen.getByText("Pick Agent A")).toBeInTheDocument();
    expect(screen.getByText("Pick Agent B")).toBeInTheDocument();
  });

  it("calls API and onWinnerPicked when picking", async () => {
    const { pickComparisonWinner } = await import("../api");

    render(
      <ComparisonResultsPanel runId={42} comparison={baseComparison} onWinnerPicked={onWinnerPicked} />,
    );

    fireEvent.click(screen.getByText("Pick Agent A"));

    await waitFor(() => {
      expect(pickComparisonWinner).toHaveBeenCalledWith(42, "a");
      expect(onWinnerPicked).toHaveBeenCalled();
    });
  });

  it("hides buttons when winner is already picked", () => {
    const withWinner: ComparisonResults = { ...baseComparison, winner: "a" };
    render(
      <ComparisonResultsPanel runId={1} comparison={withWinner} onWinnerPicked={onWinnerPicked} />,
    );
    expect(screen.queryByText("Pick Agent A")).not.toBeInTheDocument();
    expect(screen.queryByText("Pick Agent B")).not.toBeInTheDocument();
  });

  it("shows winner indicator", () => {
    const withWinner: ComparisonResults = { ...baseComparison, winner: "a" };
    render(
      <ComparisonResultsPanel runId={1} comparison={withWinner} onWinnerPicked={onWinnerPicked} />,
    );
    expect(screen.getByText("Winner: Agent A")).toBeInTheDocument();
  });

  it("displays cost and duration", () => {
    render(
      <ComparisonResultsPanel runId={1} comparison={baseComparison} onWinnerPicked={onWinnerPicked} />,
    );
    expect(screen.getByText("$0.0330")).toBeInTheDocument();
    expect(screen.getByText("121s")).toBeInTheDocument();
    expect(screen.getByText("$0.0090")).toBeInTheDocument();
    expect(screen.getByText("85s")).toBeInTheDocument();
  });
});