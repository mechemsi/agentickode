// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ToastProvider } from "../components/shared/Toast";
import PlanReviewPanel from "../components/runs/PlanReviewPanel";

vi.mock("../api/runs", () => ({
  reviewPlan: vi.fn().mockResolvedValue({ status: "approved" }),
}));

function renderWithToast(ui: React.ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

const subtasks = [
  { id: 1, title: "Implement auth", description: "Add JWT auth", files_likely_affected: ["auth.ts"] },
  { id: 2, title: "Add tests", description: "Unit tests for auth" },
];

describe("PlanReviewPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders subtask list", () => {
    renderWithToast(
      <PlanReviewPanel runId={1} subtasks={subtasks} onReviewed={() => {}} />,
    );
    expect(screen.getByText("Plan Review")).toBeInTheDocument();
    expect(screen.getByText(/1\. Implement auth/)).toBeInTheDocument();
    expect(screen.getByText(/2\. Add tests/)).toBeInTheDocument();
  });

  it("renders complexity badge when provided", () => {
    renderWithToast(
      <PlanReviewPanel runId={1} subtasks={subtasks} complexity="complex" onReviewed={() => {}} />,
    );
    expect(screen.getByText("complex")).toBeInTheDocument();
  });

  it("renders notes warning when provided", () => {
    renderWithToast(
      <PlanReviewPanel runId={1} subtasks={subtasks} notes="Watch out for X" onReviewed={() => {}} />,
    );
    expect(screen.getByText("Watch out for X")).toBeInTheDocument();
  });

  it("shows approve and reject buttons", () => {
    renderWithToast(
      <PlanReviewPanel runId={1} subtasks={subtasks} onReviewed={() => {}} />,
    );
    expect(screen.getByText(/Approve Plan/)).toBeInTheDocument();
    expect(screen.getByText("Reject")).toBeInTheDocument();
  });

  it("expands reject to show reason input", () => {
    renderWithToast(
      <PlanReviewPanel runId={1} subtasks={subtasks} onReviewed={() => {}} />,
    );
    fireEvent.click(screen.getByText("Reject"));
    expect(screen.getByPlaceholderText("Reason (optional)")).toBeInTheDocument();
    expect(screen.getByText("Confirm Reject")).toBeInTheDocument();
  });
});