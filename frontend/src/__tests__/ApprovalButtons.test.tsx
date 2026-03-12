// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import ApprovalButtons from "../components/runs/ApprovalButtons";
import { ToastProvider } from "../components/shared/Toast";

// Mock the api module
vi.mock("../api", () => ({
  approveRun: vi.fn(() => Promise.resolve()),
  rejectRun: vi.fn(() => Promise.resolve()),
}));

function renderWithToast(ui: React.ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe("ApprovalButtons", () => {
  it("renders Approve and Reject buttons", () => {
    renderWithToast(<ApprovalButtons runId={1} onAction={() => {}} />);
    expect(screen.getByText("Approve & Merge")).toBeInTheDocument();
    expect(screen.getByText("Reject")).toBeInTheDocument();
  });

  it("shows rejection form when Reject is clicked", async () => {
    const user = userEvent.setup();
    renderWithToast(<ApprovalButtons runId={1} onAction={() => {}} />);
    await user.click(screen.getByText("Reject"));
    expect(screen.getByPlaceholderText("Rejection reason...")).toBeInTheDocument();
    expect(screen.getByText("Confirm Reject")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("hides rejection form when Cancel is clicked", async () => {
    const user = userEvent.setup();
    renderWithToast(<ApprovalButtons runId={1} onAction={() => {}} />);
    await user.click(screen.getByText("Reject"));
    await user.click(screen.getByText("Cancel"));
    expect(screen.getByText("Approve & Merge")).toBeInTheDocument();
  });

  it("calls approveRun and onAction when Approve is clicked", async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    const { approveRun } = await import("../api");
    renderWithToast(<ApprovalButtons runId={42} onAction={onAction} />);
    await user.click(screen.getByText("Approve & Merge"));
    expect(approveRun).toHaveBeenCalledWith(42);
    expect(onAction).toHaveBeenCalled();
  });

  it("shows success toast on approve", async () => {
    const user = userEvent.setup();
    renderWithToast(<ApprovalButtons runId={1} onAction={() => {}} />);
    await user.click(screen.getByText("Approve & Merge"));
    expect(await screen.findByText("Run approved successfully")).toBeInTheDocument();
  });

  it("shows error toast on approve failure", async () => {
    const user = userEvent.setup();
    const { approveRun } = await import("../api");
    (approveRun as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("Server error"));
    renderWithToast(<ApprovalButtons runId={1} onAction={() => {}} />);
    await user.click(screen.getByText("Approve & Merge"));
    expect(await screen.findByText("Server error")).toBeInTheDocument();
  });
});