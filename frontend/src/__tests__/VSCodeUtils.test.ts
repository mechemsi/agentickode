// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { describe, it, expect } from "vitest";
import { getHostAlias, generateSSHConfig, generateVSCodeURI, generateJetBrainsGatewayURI } from "../utils/vscode";

describe("getHostAlias", () => {
  it("produces a slug-safe alias", () => {
    expect(getHostAlias("My Server")).toBe("agentickode-my-server");
  });

  it("replaces special characters with hyphens", () => {
    expect(getHostAlias("dev@box_1")).toBe("agentickode-dev-box-1");
  });

  it("lowercases the name", () => {
    expect(getHostAlias("PROD")).toBe("agentickode-prod");
  });

  it("handles already-clean names", () => {
    expect(getHostAlias("staging-01")).toBe("agentickode-staging-01");
  });
});

describe("generateSSHConfig", () => {
  const server = {
    name: "dev-box",
    hostname: "10.0.0.5",
    port: 2222,
    username: "root",
    worker_user: "coder",
  };

  it("includes correct Host alias", () => {
    const config = generateSSHConfig(server);
    expect(config).toContain("Host agentickode-dev-box");
  });

  it("includes HostName, Port, and User", () => {
    const config = generateSSHConfig(server);
    expect(config).toContain("HostName 10.0.0.5");
    expect(config).toContain("Port 2222");
    expect(config).toContain("User coder");
  });

  it("falls back to username when worker_user is null", () => {
    const config = generateSSHConfig({ ...server, worker_user: null });
    expect(config).toContain("User root");
  });

  it("does not include IdentityFile line", () => {
    const config = generateSSHConfig(server);
    expect(config).not.toContain("IdentityFile");
  });
});

describe("generateVSCodeURI", () => {
  const server = { hostname: "10.0.0.5", username: "root", worker_user: "coder" };

  it("produces correct vscode:// URI with user@hostname", () => {
    const uri = generateVSCodeURI(server, "/home/coder/projects/myapp");
    expect(uri).toBe(
      "vscode://vscode-remote/ssh-remote+coder@10.0.0.5/home/coder/projects/myapp",
    );
  });

  it("falls back to username when worker_user is null", () => {
    const uri = generateVSCodeURI({ ...server, worker_user: null }, "/workspace");
    expect(uri).toContain("ssh-remote+root@10.0.0.5");
  });
});

describe("generateJetBrainsGatewayURI", () => {
  const server = { hostname: "10.0.0.5", port: 22, username: "root", worker_user: "coder" };

  it("produces correct jetbrains-gateway:// URI with all params", () => {
    const uri = generateJetBrainsGatewayURI(server, "/home/coder/projects/myapp", "idea");
    expect(uri).toMatch(/^jetbrains-gateway:\/\/connect#/);
    expect(uri).toContain("type=ssh");
    expect(uri).toContain("deploy=false");
    expect(uri).toContain("host=10.0.0.5");
    expect(uri).toContain("port=22");
    expect(uri).toContain("user=coder");
    expect(uri).toContain("ide=idea");
    expect(uri).toContain("projectPath=/home/coder/projects/myapp");
  });

  it("uses worker_user over username", () => {
    const uri = generateJetBrainsGatewayURI(server, "/workspace", "webstorm");
    expect(uri).toContain("user=coder");
  });

  it("falls back to username when worker_user is null", () => {
    const uri = generateJetBrainsGatewayURI({ ...server, worker_user: null }, "/workspace", "idea");
    expect(uri).toContain("user=root");
  });

  it("respects IDE parameter", () => {
    const uri = generateJetBrainsGatewayURI(server, "/workspace", "pycharm");
    expect(uri).toContain("ide=pycharm");
  });
});