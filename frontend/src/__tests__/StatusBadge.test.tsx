// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import StatusBadge from "../components/shared/StatusBadge";

describe("StatusBadge", () => {
  it("renders the status text with underscores replaced", () => {
    render(<StatusBadge status="awaiting_approval" />);
    expect(screen.getByText("awaiting approval")).toBeInTheDocument();
  });

  it("applies correct color class for pending", () => {
    const { container } = render(<StatusBadge status="pending" />);
    const badge = container.querySelector("span");
    expect(badge).toHaveClass("text-yellow-300");
  });

  it("applies correct color class for completed", () => {
    const { container } = render(<StatusBadge status="completed" />);
    const badge = container.querySelector("span");
    expect(badge).toHaveClass("text-green-300");
  });

  it("applies correct color class for failed", () => {
    const { container } = render(<StatusBadge status="failed" />);
    const badge = container.querySelector("span");
    expect(badge).toHaveClass("text-red-300");
  });

  it("uses fallback color for unknown status", () => {
    const { container } = render(<StatusBadge status="unknown" />);
    const badge = container.querySelector("span");
    expect(badge).toHaveClass("text-gray-300");
  });
});