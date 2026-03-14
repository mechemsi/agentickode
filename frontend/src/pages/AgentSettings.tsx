// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useState } from "react";
import { Bot, ChevronDown, ChevronUp, Server } from "lucide-react";
import { getAgents, getAgentAvailability, updateAgent } from "../api";
import type { AgentSettings } from "../types";
import { useToast } from "../components/shared/Toast";
import { KVEditor, parseKV, kvToObject } from "../components/shared/KVEditor";
import type { KVEntry } from "../components/shared/KVEditor";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  ariaLabel: string;
}

function Toggle({ checked, onChange, ariaLabel }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex w-11 h-6 rounded-full transition-colors ${
        checked ? "bg-blue-600" : "bg-gray-700"
      }`}
      aria-label={ariaLabel}
    >
      <span
        className={`absolute left-0.5 top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

interface AvailabilityEntry {
  workspace_server_id: number;
  version: string | null;
  path: string | null;
}

interface AgentCardProps {
  agent: AgentSettings;
  onSaved: () => void;
}

function AgentCard({ agent, onSaved }: AgentCardProps) {
  const toast = useToast();
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [availability, setAvailability] = useState<AvailabilityEntry[] | null>(null);
  const [loadingAvail, setLoadingAvail] = useState(false);

  // Local edit state
  const [displayName, setDisplayName] = useState(agent.display_name);
  const [description, setDescription] = useState(agent.description);
  const [supportsSession, setSupportsSession] = useState(agent.supports_session);
  const [defaultTimeout, setDefaultTimeout] = useState(String(agent.default_timeout));
  const [maxRetries, setMaxRetries] = useState(String(agent.max_retries));
  const [enabled, setEnabled] = useState(agent.enabled);
  const [envVars, setEnvVars] = useState<KVEntry[]>(
    parseKV(agent.environment_vars as Record<string, string | boolean>),
  );
  const [cliFlags, setCliFlags] = useState<KVEntry[]>(
    parseKV(agent.cli_flags as Record<string, string | boolean>),
  );
  const [commandTemplates, setCommandTemplates] = useState<KVEntry[]>(
    parseKV(agent.command_templates as Record<string, string | boolean>),
  );
  const [agentType, setAgentType] = useState(agent.agent_type ?? "cli_binary");
  const [installCmd, setInstallCmd] = useState(agent.install_cmd ?? "");
  const [postInstallCmd, setPostInstallCmd] = useState(agent.post_install_cmd ?? "");
  const [checkCmd, setCheckCmd] = useState(agent.check_cmd ?? "");
  const [prereqCheck, setPrereqCheck] = useState(agent.prereq_check ?? "");
  const [prereqName, setPrereqName] = useState(agent.prereq_name ?? "");
  const [needsNonRoot, setNeedsNonRoot] = useState(agent.needs_non_root ?? false);
  const [consolidatedDefault, setConsolidatedDefault] = useState(agent.consolidated_default ?? true);

  // Sync when agent prop changes
  useEffect(() => {
    setDisplayName(agent.display_name);
    setDescription(agent.description);
    setSupportsSession(agent.supports_session);
    setDefaultTimeout(String(agent.default_timeout));
    setMaxRetries(String(agent.max_retries));
    setEnabled(agent.enabled);
    setEnvVars(parseKV(agent.environment_vars as Record<string, string | boolean>));
    setCliFlags(parseKV(agent.cli_flags as Record<string, string | boolean>));
    setCommandTemplates(parseKV(agent.command_templates as Record<string, string | boolean>));
    setAgentType(agent.agent_type ?? "cli_binary");
    setInstallCmd(agent.install_cmd ?? "");
    setPostInstallCmd(agent.post_install_cmd ?? "");
    setCheckCmd(agent.check_cmd ?? "");
    setPrereqCheck(agent.prereq_check ?? "");
    setPrereqName(agent.prereq_name ?? "");
    setNeedsNonRoot(agent.needs_non_root ?? false);
    setConsolidatedDefault(agent.consolidated_default ?? true);
  }, [agent]);

  const loadAvailability = async () => {
    if (availability !== null) return;
    setLoadingAvail(true);
    try {
      const data = await getAgentAvailability(agent.agent_name);
      setAvailability(data);
    } catch {
      setAvailability([]);
    } finally {
      setLoadingAvail(false);
    }
  };

  const handleExpand = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) loadAvailability();
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const timeout = parseInt(defaultTimeout, 10);
      const retries = parseInt(maxRetries, 10);
      if (isNaN(timeout) || timeout <= 0) {
        toast.error("Timeout must be a positive number");
        return;
      }
      if (isNaN(retries) || retries < 0) {
        toast.error("Max retries must be a non-negative number");
        return;
      }
      await updateAgent(agent.agent_name, {
        display_name: displayName,
        description,
        supports_session: supportsSession,
        default_timeout: timeout,
        max_retries: retries,
        enabled,
        environment_vars: kvToObject(envVars),
        cli_flags: kvToObject(cliFlags),
        command_templates: kvToObject(commandTemplates),
        agent_type: agentType,
        install_cmd: installCmd || null,
        post_install_cmd: postInstallCmd || null,
        check_cmd: checkCmd || null,
        prereq_check: prereqCheck || null,
        prereq_name: prereqName || null,
        needs_non_root: needsNonRoot,
        consolidated_default: consolidatedDefault,
      });
      toast.success(`Saved ${agent.display_name}`);
      onSaved();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-gray-900/40 border border-gray-800/60 rounded-xl backdrop-blur-sm">
      {/* Header */}
      <button
        onClick={handleExpand}
        className="w-full flex items-center justify-between p-4 text-left"
      >
        <div className="flex items-center gap-3">
          <Bot className="w-4 h-4 text-gray-500 flex-shrink-0" />
          <span className="text-sm font-medium">{agent.display_name}</span>
          <span className="text-xs px-2 py-0.5 rounded-full text-gray-500 bg-gray-800 font-mono">
            {agent.agent_name}
          </span>
          {!agent.enabled && (
            <span className="text-xs px-2 py-0.5 rounded-full text-red-400 bg-red-500/10">
              Disabled
            </span>
          )}
          {agent.supports_session && (
            <span className="text-xs px-2 py-0.5 rounded-full text-blue-400 bg-blue-500/10">
              Sessions
            </span>
          )}
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-gray-500 flex-shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-gray-800/60 p-4 space-y-4">
          {/* Top row: enabled toggle */}
          <div className="flex items-center justify-between">
            <label className="text-xs text-gray-400">Enabled</label>
            <Toggle checked={enabled} onChange={setEnabled} ariaLabel="Toggle enabled" />
          </div>

          {/* Display name */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            />
          </div>

          {/* Numeric params */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Default timeout (seconds)
              </label>
              <input
                type="number"
                min={1}
                value={defaultTimeout}
                onChange={(e) => setDefaultTimeout(e.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Max retries</label>
              <input
                type="number"
                min={0}
                value={maxRetries}
                onChange={(e) => setMaxRetries(e.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
              />
            </div>
          </div>

          {/* Session support */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs text-gray-400">Session support</label>
              <p className="text-xs text-gray-600 mt-0.5">
                Allow resuming previous agent sessions
              </p>
            </div>
            <Toggle
              checked={supportsSession}
              onChange={setSupportsSession}
              ariaLabel="Toggle session support"
            />
          </div>

          {/* CLI Flags */}
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">CLI Flags</label>
            <p className="text-xs text-gray-600 mb-2">
              Extra flags appended to every command (e.g. <code className="text-gray-500">--model</code>, <code className="text-gray-500">opus</code>)
            </p>
            <KVEditor entries={cliFlags} onChange={setCliFlags} />
          </div>

          {/* Command Templates */}
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">Command Templates</label>
            <p className="text-xs text-gray-600 mb-2">
              Shell commands used for each operation. Placeholders:{" "}
              <code className="text-gray-500">{"{workspace}"}</code>,{" "}
              <code className="text-gray-500">{"{prompt_file}"}</code>,{" "}
              <code className="text-gray-500">{"{instruction_file}"}</code>,{" "}
              <code className="text-gray-500">{"{session_id}"}</code>
            </p>
            <KVEditor entries={commandTemplates} onChange={setCommandTemplates} />
          </div>

          {/* Environment Variables */}
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">Environment Variables</label>
            <p className="text-xs text-gray-600 mb-2">
              Injected into agent execution environment
            </p>
            <KVEditor entries={envVars} onChange={setEnvVars} maskValues />
          </div>

          {/* Installation */}
          <div>
            <label className="block text-xs text-gray-400 mb-2 font-medium">Installation</label>
            <div className="space-y-3 pl-1">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Agent Type</label>
                  <select
                    value={agentType}
                    onChange={(e) => setAgentType(e.target.value)}
                    className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                  >
                    <option value="cli_binary">cli_binary</option>
                    <option value="api_service">api_service</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Prerequisite Name</label>
                  <input
                    type="text"
                    value={prereqName}
                    onChange={(e) => setPrereqName(e.target.value)}
                    placeholder="e.g. curl"
                    className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Check Command</label>
                <input
                  type="text"
                  value={checkCmd}
                  onChange={(e) => setCheckCmd(e.target.value)}
                  placeholder="e.g. command -v claude"
                  className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Install Command</label>
                <p className="text-xs text-gray-600 mb-1">Binary install (runs first, no auth needed)</p>
                <textarea
                  value={installCmd}
                  onChange={(e) => setInstallCmd(e.target.value)}
                  placeholder="e.g. curl -fsSL https://... | bash"
                  rows={3}
                  className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-y"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Post-Install Command</label>
                <p className="text-xs text-gray-600 mb-1">Plugins, tools, extensions (runs after credentials are synced)</p>
                <textarea
                  value={postInstallCmd}
                  onChange={(e) => setPostInstallCmd(e.target.value)}
                  placeholder="e.g. claude plugin install ... || true"
                  rows={3}
                  className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-y"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Prerequisite Check</label>
                <input
                  type="text"
                  value={prereqCheck}
                  onChange={(e) => setPrereqCheck(e.target.value)}
                  placeholder="e.g. command -v curl"
                  className="w-full px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs text-gray-500">Needs Non-Root User</label>
                  <p className="text-xs text-gray-600 mt-0.5">
                    Run agent as a non-root worker user
                  </p>
                </div>
                <Toggle
                  checked={needsNonRoot}
                  onChange={setNeedsNonRoot}
                  ariaLabel="Toggle needs non-root"
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs text-gray-500">Consolidated Mode</label>
                  <p className="text-xs text-gray-600 mt-0.5">
                    Plan + code + review in a single invocation
                  </p>
                </div>
                <Toggle
                  checked={consolidatedDefault}
                  onChange={setConsolidatedDefault}
                  ariaLabel="Toggle consolidated mode"
                />
              </div>
            </div>
          </div>

          {/* Availability */}
          <div>
            <label className="block text-xs text-gray-400 mb-2 flex items-center gap-1.5">
              <Server className="w-3.5 h-3.5" />
              Available on workspace servers
            </label>
            {loadingAvail && (
              <p className="text-xs text-gray-500">Loading availability...</p>
            )}
            {!loadingAvail && availability !== null && availability.length === 0 && (
              <p className="text-xs text-gray-600">
                Not found on any workspace server
              </p>
            )}
            {!loadingAvail && availability && availability.length > 0 && (
              <div className="space-y-1">
                {availability.map((a) => (
                  <div
                    key={a.workspace_server_id}
                    className="flex items-center gap-2 text-xs text-gray-400"
                  >
                    <span className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
                    <span>Server #{a.workspace_server_id}</span>
                    {a.version && (
                      <span className="text-gray-600">v{a.version}</span>
                    )}
                    {a.path && (
                      <span className="text-gray-700 font-mono truncate">{a.path}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Save */}
          <div className="flex justify-end pt-2 border-t border-gray-800/40">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentSettingsPage() {
  const [agents, setAgents] = useState<AgentSettings[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setAgents(await getAgents());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Bot className="w-5 h-5 text-blue-400" />
          Agents
        </h1>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-800/50 rounded-xl p-4 mb-5 text-sm text-red-300">
          {error}
        </div>
      )}

      {agents.length === 0 && !error && (
        <div className="text-center py-12 text-gray-500 text-sm">
          No agents configured. Start the backend to seed defaults.
        </div>
      )}

      <div className="space-y-3">
        {agents.map((agent) => (
          <AgentCard key={agent.agent_name} agent={agent} onSaved={load} />
        ))}
      </div>
    </>
  );
}