// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import Nav from "../components/shared/Nav";

describe("Nav", () => {
  it("renders all navigation links", () => {
    render(<MemoryRouter><Nav /></MemoryRouter>);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("Servers")).toBeInTheDocument();
    expect(screen.getByText("Roles")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("renders AutoDev brand name", () => {
    render(<MemoryRouter><Nav /></MemoryRouter>);
    expect(screen.getByText("AutoDev")).toBeInTheDocument();
  });

  it("highlights active link", () => {
    render(<MemoryRouter initialEntries={["/projects"]}><Nav /></MemoryRouter>);
    const projectsLink = screen.getByText("Projects");
    expect(projectsLink).toHaveClass("bg-gray-800");
  });
});