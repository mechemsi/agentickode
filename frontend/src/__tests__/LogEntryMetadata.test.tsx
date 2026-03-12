// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import LogEntryMetadata from "../components/runs/LogEntryMetadata";

describe("LogEntryMetadata", () => {
  it("renders collapsed by default with category label", () => {
    render(<LogEntryMetadata metadata={{ category: "ssh_command", command: "git status" }} />);
    expect(screen.getByText("SSH Command")).toBeInTheDocument();
    expect(screen.queryByTestId("metadata-content")).not.toBeInTheDocument();
  });

  it("expands and shows content when clicked", () => {
    render(<LogEntryMetadata metadata={{ category: "prompt", prompt_text: "Hello world" }} />);
    fireEvent.click(screen.getByTestId("metadata-toggle"));
    expect(screen.getByTestId("metadata-content")).toBeInTheDocument();
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("collapses when clicked again", () => {
    render(<LogEntryMetadata metadata={{ category: "response", response_text: "Some response" }} />);
    fireEvent.click(screen.getByTestId("metadata-toggle"));
    expect(screen.getByTestId("metadata-content")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("metadata-toggle"));
    expect(screen.queryByTestId("metadata-content")).not.toBeInTheDocument();
  });

  it("shows truncation warning", () => {
    render(
      <LogEntryMetadata
        metadata={{
          category: "prompt",
          prompt_text: "truncated...",
          prompt_text_truncated: true,
          prompt_text_original_length: 15000,
        }}
      />
    );
    fireEvent.click(screen.getByTestId("metadata-toggle"));
    expect(screen.getByText(/original: 15000 chars/)).toBeInTheDocument();
  });

  it("renders category labels correctly", () => {
    const { rerender } = render(
      <LogEntryMetadata metadata={{ category: "ssh_command" }} />
    );
    expect(screen.getByText("SSH Command")).toBeInTheDocument();

    rerender(<LogEntryMetadata metadata={{ category: "system_prompt" }} />);
    expect(screen.getByText("System Prompt")).toBeInTheDocument();

    rerender(<LogEntryMetadata metadata={{ category: "prompt" }} />);
    expect(screen.getByText("Prompt")).toBeInTheDocument();

    rerender(<LogEntryMetadata metadata={{ category: "response" }} />);
    expect(screen.getByText("Response")).toBeInTheDocument();
  });

  it("renders key-value pairs for non-text fields", () => {
    render(
      <LogEntryMetadata metadata={{ category: "ssh_command", exit_code: 0, command: "ls" }} />
    );
    fireEvent.click(screen.getByTestId("metadata-toggle"));
    expect(screen.getByText("exit_code:")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("falls back to 'Details' for unknown category", () => {
    render(<LogEntryMetadata metadata={{ category: "unknown_type" }} />);
    expect(screen.getByText("unknown_type")).toBeInTheDocument();
  });
});