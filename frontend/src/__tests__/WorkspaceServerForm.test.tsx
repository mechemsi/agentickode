// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import WorkspaceServerForm from "../components/servers/WorkspaceServerForm";

describe("WorkspaceServerForm", () => {
  it("renders all form fields", () => {
    render(<WorkspaceServerForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("hostname")).toBeInTheDocument();
    expect(screen.getByText("port")).toBeInTheDocument();
    expect(screen.getByText("SSH admin user")).toBeInTheDocument();
    expect(screen.getByText("ssh_key_path")).toBeInTheDocument();
    expect(screen.getByText("worker user")).toBeInTheDocument();
  });

  it("has correct defaults", () => {
    render(<WorkspaceServerForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByDisplayValue("22")).toBeInTheDocument();
    expect(screen.getByDisplayValue("root")).toBeInTheDocument();
    expect(screen.getByDisplayValue("coder")).toBeInTheDocument();
  });

  it("calls onSubmit when save clicked", () => {
    const onSubmit = vi.fn();
    render(<WorkspaceServerForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("Save"));
    expect(onSubmit).toHaveBeenCalled();
  });

  it("calls onCancel when cancel clicked", () => {
    const onCancel = vi.fn();
    render(<WorkspaceServerForm onSubmit={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("shows Saving... when loading", () => {
    render(<WorkspaceServerForm onSubmit={vi.fn()} onCancel={vi.fn()} loading />);
    expect(screen.getByText("Saving...")).toBeInTheDocument();
  });

  it("populates initial values", () => {
    render(
      <WorkspaceServerForm
        initial={{ name: "test-server", hostname: "192.168.1.1" }}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue("test-server")).toBeInTheDocument();
    expect(screen.getByDisplayValue("192.168.1.1")).toBeInTheDocument();
  });
});