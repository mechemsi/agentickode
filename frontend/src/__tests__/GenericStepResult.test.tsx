// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import GenericStepResult from "../components/runs/GenericStepResult";

describe("GenericStepResult", () => {
  it("renders bash result with command, exit code, and stdout", () => {
    render(
      <GenericStepResult
        phaseName="build"
        kind="bash"
        data={{
          command: "make build",
          stdout: "compiling...\ndone",
          stderr: "",
          exit_code: 0,
        }}
      />,
    );
    expect(screen.getByText("build")).toBeInTheDocument();
    expect(screen.getByText("exit 0")).toBeInTheDocument();
    expect(screen.getByText(/\$ make build/)).toBeInTheDocument();
    expect(screen.getByText(/compiling/)).toBeInTheDocument();
  });

  it("flags bash skipped with non-zero exit", () => {
    render(
      <GenericStepResult
        phaseName="deploy"
        kind="bash"
        data={{
          command: "./deploy.sh",
          stdout: "",
          stderr: "no key",
          exit_code: 1,
          skipped: true,
        }}
      />,
    );
    expect(screen.getByText("exit 1 (skipped)")).toBeInTheDocument();
    expect(screen.getByText(/no key/)).toBeInTheDocument();
  });

  it("renders agent result with provider/role/mode badges and string response", () => {
    render(
      <GenericStepResult
        phaseName="ask"
        kind="agent"
        data={{
          provider: "agent/claude",
          role: "coder",
          mode: "generate",
          response: "Looks fine.",
        }}
      />,
    );
    expect(screen.getByText("ask")).toBeInTheDocument();
    expect(screen.getByText("agent/claude")).toBeInTheDocument();
    expect(screen.getByText("role: coder")).toBeInTheDocument();
    expect(screen.getByText("mode: generate")).toBeInTheDocument();
    expect(screen.getByText("Looks fine.")).toBeInTheDocument();
  });

  it("renders agent task result as collapsible JSON when response is an object", () => {
    render(
      <GenericStepResult
        phaseName="implement"
        kind="agent"
        data={{
          provider: "agent/codex",
          role: "coder",
          mode: "task",
          response: { exit_code: 0, files_changed: ["a.py"] },
          session_id: "abcdef0123456789",
        }}
      />,
    );
    expect(screen.getByText("agent/codex")).toBeInTheDocument();
    // Session id is truncated to 8 chars + ellipsis
    expect(screen.getByText("abcdef01…")).toBeInTheDocument();
    // Response panel title comes from CollapsibleJSON (prefixed with ▸ glyph)
    expect(screen.getByText(/Response/)).toBeInTheDocument();
  });

  it("falls back to CollapsibleJSON for legacy_phase kind", () => {
    render(
      <GenericStepResult
        phaseName="planning"
        kind="legacy_phase"
        data={{ subtasks: [{ id: 1 }] }}
      />,
    );
    expect(screen.getByText(/Planning Result/)).toBeInTheDocument();
  });
});
