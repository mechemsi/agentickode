// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import FilterBar from "../components/shared/FilterBar";

describe("FilterBar", () => {
  it("renders all status filter buttons", () => {
    render(<FilterBar value="" onChange={() => {}} />);
    expect(screen.getByText("All")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("highlights the active filter", () => {
    const { container } = render(<FilterBar value="running" onChange={() => {}} />);
    const buttons = container.querySelectorAll("button");
    const runningBtn = Array.from(buttons).find((b) => b.textContent === "running");
    expect(runningBtn).toHaveClass("bg-blue-600/20");
  });

  it("calls onChange when a filter is clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FilterBar value="" onChange={onChange} />);
    await user.click(screen.getByText("failed"));
    expect(onChange).toHaveBeenCalledWith("failed");
  });

  it("calls onChange with empty string for All button", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FilterBar value="pending" onChange={onChange} />);
    await user.click(screen.getByText("All"));
    expect(onChange).toHaveBeenCalledWith("");
  });
});