// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CollapsibleJSON from "../components/shared/CollapsibleJSON";

describe("CollapsibleJSON", () => {
  it("shows title but not content initially", () => {
    render(<CollapsibleJSON title="Test Data" data={{ key: "value" }} />);
    expect(screen.getByText(/Test Data/)).toBeInTheDocument();
    expect(screen.queryByText('"key"')).not.toBeInTheDocument();
  });

  it("shows content after clicking toggle", () => {
    render(<CollapsibleJSON title="Test Data" data={{ key: "value" }} />);
    fireEvent.click(screen.getByText(/Test Data/));
    expect(screen.getByText(/"key"/)).toBeInTheDocument();
  });

  it("hides content after clicking toggle twice", () => {
    render(<CollapsibleJSON title="Test Data" data={{ key: "value" }} />);
    const btn = screen.getByText(/Test Data/);
    fireEvent.click(btn);
    expect(screen.getByText(/"key"/)).toBeInTheDocument();
    fireEvent.click(btn);
    expect(screen.queryByText(/"key"/)).not.toBeInTheDocument();
  });
});