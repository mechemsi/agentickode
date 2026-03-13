// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

/** Generate a slug-safe SSH config Host alias from a server name. */
export function getHostAlias(serverName: string): string {
  return `agentickode-${serverName.toLowerCase().replace(/[^a-z0-9-]/g, "-")}`;
}

/** Generate ~/.ssh/config snippet for a workspace server. */
export function generateSSHConfig(server: {
  name: string;
  hostname: string;
  port: number;
  username: string;
  worker_user: string | null;
}): string {
  const alias = getHostAlias(server.name);
  const user = server.worker_user || server.username;
  return [
    `Host ${alias}`,
    `  HostName ${server.hostname}`,
    `  Port ${server.port}`,
    `  User ${user}`,
  ].join("\n");
}

/** Generate vscode:// URI for opening a remote folder via SSH using user@hostname. */
export function generateVSCodeURI(
  server: { hostname: string; username: string; worker_user: string | null },
  remotePath: string,
): string {
  const user = server.worker_user || server.username;
  return `vscode://vscode-remote/ssh-remote+${user}@${server.hostname}${remotePath}`;
}

/** Supported JetBrains IDE identifiers for Gateway. */
export type JetBrainsIDE =
  | "idea"
  | "pycharm"
  | "webstorm"
  | "goland"
  | "phpstorm"
  | "rubymine"
  | "rider"
  | "clion";

/** IDE options for dropdown rendering. */
export const JETBRAINS_IDES: { id: JetBrainsIDE; label: string }[] = [
  { id: "idea", label: "IntelliJ IDEA" },
  { id: "pycharm", label: "PyCharm" },
  { id: "webstorm", label: "WebStorm" },
  { id: "goland", label: "GoLand" },
  { id: "phpstorm", label: "PhpStorm" },
  { id: "rubymine", label: "RubyMine" },
  { id: "rider", label: "Rider" },
  { id: "clion", label: "CLion" },
];

/** Generate jetbrains-gateway:// URI for opening a remote folder via SSH. */
export function generateJetBrainsGatewayURI(
  server: { hostname: string; port: number; username: string; worker_user: string | null },
  remotePath: string,
  ide: JetBrainsIDE,
): string {
  const user = server.worker_user || server.username;
  // Build fragment manually — URLSearchParams encodes slashes in projectPath
  // which JetBrains Gateway doesn't expect.
  const fragment = [
    `type=ssh`,
    `deploy=false`,
    `projectPath=${remotePath}`,
    `host=${server.hostname}`,
    `port=${server.port}`,
    `user=${user}`,
    `ide=${ide}`,
  ].join("&");
  return `jetbrains-gateway://connect#${fragment}`;
}