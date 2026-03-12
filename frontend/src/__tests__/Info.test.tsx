// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Info from "../components/shared/Info";

describe("Info", () => {
  it("renders label and value", () => {
    render(<Info label="Branch" value="feature/ai-1" />);
    expect(screen.getByText("Branch:")).toBeInTheDocument();
    expect(screen.getByText("feature/ai-1")).toBeInTheDocument();
  });

  it("renders JSX value", () => {
    render(<Info label="Error" value={<span data-testid="err">Something broke</span>} />);
    expect(screen.getByTestId("err")).toHaveTextContent("Something broke");
  });
});