// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import OllamaServerForm from "../components/settings/OllamaServerForm";

describe("OllamaServerForm", () => {
  it("renders name and url fields", () => {
    render(<OllamaServerForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("url")).toBeInTheDocument();
  });

  it("has correct defaults", () => {
    render(<OllamaServerForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByDisplayValue("http://")).toBeInTheDocument();
  });

  it("calls onSubmit when save clicked", () => {
    const onSubmit = vi.fn();
    render(<OllamaServerForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("Save"));
    expect(onSubmit).toHaveBeenCalled();
  });

  it("calls onCancel when cancel clicked", () => {
    const onCancel = vi.fn();
    render(<OllamaServerForm onSubmit={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("populates initial values", () => {
    render(
      <OllamaServerForm
        initial={{ name: "gpu-01", url: "http://10.10.50.20:11434" }}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue("gpu-01")).toBeInTheDocument();
    expect(screen.getByDisplayValue("http://10.10.50.20:11434")).toBeInTheDocument();
  });
});