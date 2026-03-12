// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockCheckGitAccess = vi.fn();
const mockGenerateGitKey = vi.fn();

vi.mock("../api", () => ({
  checkGitAccess: (...args: unknown[]) => mockCheckGitAccess(...args),
  generateGitKey: (...args: unknown[]) => mockGenerateGitKey(...args),
}));

import GitAccessPanel from "../components/servers/GitAccessPanel";

describe("GitAccessPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    mockCheckGitAccess.mockReturnValue(new Promise(() => {})); // never resolves
    render(<GitAccessPanel serverId={1} />);
    expect(screen.getByText("Checking git access...")).toBeInTheDocument();
  });

  it("renders public key when present", async () => {
    mockCheckGitAccess.mockResolvedValue({
      has_key: true,
      public_key: "ssh-ed25519 AAAA test@host",
      key_type: "ed25519",
      providers: [
        { host: "github.com", name: "GitHub", connected: true, username: "octocat", error: null },
        { host: "gitlab.com", name: "GitLab", connected: false, username: null, error: "Permission denied" },
      ],
    });

    render(<GitAccessPanel serverId={1} />);

    expect(await screen.findByText("ssh-ed25519 AAAA test@host")).toBeInTheDocument();
    expect(screen.getByText("ed25519")).toBeInTheDocument();
    expect(screen.getByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("octocat")).toBeInTheDocument();
    expect(screen.getByText("GitLab")).toBeInTheDocument();
  });

  it("shows generate button when no key exists", async () => {
    mockCheckGitAccess.mockResolvedValue({
      has_key: false,
      public_key: null,
      key_type: null,
      providers: [
        { host: "github.com", name: "GitHub", connected: false, username: null, error: "No SSH key found" },
      ],
    });

    render(<GitAccessPanel serverId={1} />);

    expect(await screen.findByText("No SSH key found on server")).toBeInTheDocument();
    expect(screen.getByText("Generate Key")).toBeInTheDocument();
  });

  it("calls generateGitKey on Generate Key click", async () => {
    mockCheckGitAccess.mockResolvedValue({
      has_key: false,
      public_key: null,
      key_type: null,
      providers: [],
    });
    mockGenerateGitKey.mockResolvedValue({
      has_key: true,
      public_key: "ssh-ed25519 NEWKEY autodev@srv",
      key_type: "ed25519",
      providers: [],
    });

    render(<GitAccessPanel serverId={1} />);

    expect(await screen.findByText("Generate Key")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Generate Key"));

    await waitFor(() => {
      expect(mockGenerateGitKey).toHaveBeenCalledWith(1);
    });
  });

  it("renders provider badges with correct status", async () => {
    mockCheckGitAccess.mockResolvedValue({
      has_key: true,
      public_key: "ssh-ed25519 AAAA test@host",
      key_type: "ed25519",
      providers: [
        { host: "github.com", name: "GitHub", connected: true, username: "user1", error: null },
        { host: "gitlab.com", name: "GitLab", connected: false, username: null, error: "denied" },
        { host: "bitbucket.org", name: "Bitbucket", connected: false, username: null, error: "denied" },
      ],
    });

    render(<GitAccessPanel serverId={1} />);

    expect(await screen.findByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("user1")).toBeInTheDocument();
    expect(screen.getByText("GitLab")).toBeInTheDocument();
    expect(screen.getByText("Bitbucket")).toBeInTheDocument();
    expect(screen.getByText("Test All")).toBeInTheDocument();
  });
});