// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { CheckCircle, GitBranch, Globe, Key, Link, Server, Tag, XCircle, Zap } from "lucide-react";
import { parseGitUrl, testConnection } from "../../api";
import type { GitUrlParseResponse, ProjectConfig, WorkspaceServer } from "../../types";

const CLS = "bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 w-full";

const TASK_SOURCES = [
  { value: "plain", label: "Manual (API only)" },
  { value: "github", label: "GitHub Issues" },
  { value: "gitea", label: "Gitea Issues" },
  { value: "gitlab", label: "GitLab Issues" },
  { value: "plane", label: "Plane" },
  { value: "notion", label: "Notion" },
];

const POLL_CAPABLE_SOURCES = new Set(["github", "gitea", "gitlab", "plane", "notion"]);
const GIT_PROVIDERS = [
  { value: "github", label: "GitHub" },
  { value: "gitlab", label: "GitLab" },
  { value: "gitea", label: "Gitea" },
  { value: "bitbucket", label: "Bitbucket" },
];

function defaultTaskSource(p: string) {
  return ["github", "gitea", "gitlab"].includes(p) ? p : "plain";
}

type Status = { ok: boolean; msg: string };
type NotionFields = {
  notion_api_key: string;
  notion_database_id: string;
  notion_status_property: string;
  notion_tag_property: string;
  notion_title_property: string;
};
type FD = {
  project_id: string;
  project_slug: string;
  repo_owner: string;
  repo_name: string;
  default_branch: string;
  task_source: string;
  git_provider: string;
  workspace_server_ids: number[];
  git_provider_token: string;
  poll_enabled: boolean;
  poll_interval_minutes: number;
  notion: NotionFields;
};
type Initial = Partial<Omit<ProjectConfig, "created_at" | "updated_at" | "workspace_config" | "ai_config">>;

function Field({ label, icon: Icon, children }: { label: string; icon?: React.ElementType; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-gray-400 inline-flex items-center gap-1">{Icon && <Icon className="w-3 h-3" />}{label}</span>
      {children}
    </label>
  );
}

function StatusLine({ s }: { s: Status }) {
  return (
    <span className={`text-xs flex items-center gap-1 ${s.ok ? "text-green-400" : "text-red-400"}`}>
      {s.ok ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}{s.msg}
    </span>
  );
}

function UrlSection({ gitUrl, setGitUrl, onParsed, workspaceServerId }: { gitUrl: string; setGitUrl: (v: string) => void; onParsed: (r: GitUrlParseResponse) => void; workspaceServerId?: number | null }) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const parse = async () => {
    if (!gitUrl.trim()) { setStatus({ ok: false, msg: "Enter a git URL first" }); return; }
    setLoading(true); setStatus(null);
    try {
      const r = await parseGitUrl(gitUrl.trim(), workspaceServerId);
      setStatus({ ok: true, msg: `Repo found: ${r.owner}/${r.repo} (${r.default_branch})` });
      onParsed(r);
    } catch (e) { setStatus({ ok: false, msg: e instanceof Error ? e.message : "Parse failed" }); }
    finally { setLoading(false); }
  };
  return (
    <div className="col-span-1 sm:col-span-2 flex flex-col gap-2">
      <span className="text-xs text-gray-400 inline-flex items-center gap-1"><Link className="w-3 h-3" />Git Repository URL</span>
      <div className="flex gap-2">
        <input className={CLS} placeholder="https://github.com/owner/repo" value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && parse()} />
        <button onClick={parse} disabled={loading} className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm whitespace-nowrap focus:outline-none focus:ring-2 focus:ring-indigo-500/40">
          {loading ? "Parsing…" : "Parse"}
        </button>
      </div>
      {status && <StatusLine s={status} />}
    </div>
  );
}

export default function ProjectForm({ initial, onSubmit, onCancel, servers = [] }: { initial?: Initial; onSubmit: (d: Record<string, unknown>) => void; onCancel: () => void; servers?: WorkspaceServer[] }) {
  const isEdit = !!initial;
  const [gitUrl, setGitUrl] = useState("");
  const [parsed, setParsed] = useState(false);
  const [providerHost, setProviderHost] = useState("");
  const [connStatus, setConnStatus] = useState<Status | null>(null);
  const [saveErr, setSaveErr] = useState("");
  const integrationCfg = (initial?.integration_config ?? {}) as Record<string, unknown>;
  const [form, setForm] = useState<FD>({
    project_id: initial?.project_id ?? "",
    project_slug: initial?.project_slug ?? "",
    repo_owner: initial?.repo_owner ?? "",
    repo_name: initial?.repo_name ?? "",
    default_branch: initial?.default_branch ?? "main",
    task_source: initial?.task_source ?? "plain",
    git_provider: initial?.git_provider ?? "gitea",
    workspace_server_ids: initial?.workspace_server_ids ?? [],
    git_provider_token: "",
    poll_enabled: initial?.poll_enabled ?? false,
    poll_interval_minutes: initial?.poll_interval_minutes ?? 5,
    notion: {
      notion_api_key: "",
      notion_database_id: String(integrationCfg["notion_database_id"] ?? ""),
      notion_status_property: String(integrationCfg["notion_status_property"] ?? "Status"),
      notion_tag_property: String(integrationCfg["notion_tag_property"] ?? "Tags"),
      notion_title_property: String(integrationCfg["notion_title_property"] ?? "Name"),
    },
  });
  const hasNotionKey = Boolean(integrationCfg["has_notion_api_key"]);
  const set = (k: keyof FD, v: string | number | boolean | null | number[]) =>
    setForm((p) => ({ ...p, [k]: v }));
  const setNotion = (k: keyof NotionFields, v: string) =>
    setForm((p) => ({ ...p, notion: { ...p.notion, [k]: v } }));

  const handleParsed = (r: GitUrlParseResponse) => {
    setParsed(true);
    setProviderHost(r.provider_confirmed ? "" : r.host);
    setForm((p) => ({ ...p, project_id: r.suggested_id, project_slug: r.suggested_slug, repo_owner: r.owner, repo_name: r.repo, default_branch: r.default_branch, git_provider: r.provider, task_source: defaultTaskSource(r.provider) }));
  };

  const handleTestConn = async () => {
    const firstServer = form.workspace_server_ids[0] ?? null;
    if (!firstServer) { setConnStatus({ ok: false, msg: "Select a workspace server first" }); return; }
    setConnStatus(null);
    try {
      const url = isEdit ? `https://placeholder/${form.repo_owner}/${form.repo_name}` : gitUrl;
      const r = await testConnection(firstServer, url);
      setConnStatus(r.success ? { ok: true, msg: "SSH connection OK" } : { ok: false, msg: r.error ?? "Connection failed" });
    } catch (e) { setConnStatus({ ok: false, msg: e instanceof Error ? e.message : "Connection failed" }); }
  };

  const handleSave = () => {
    if (!isEdit && !parsed && form.task_source !== "notion") {
      setSaveErr("Parse git URL first");
      return;
    }
    setSaveErr("");
    const { notion, ...rest } = form;
    const data: Record<string, unknown> = { ...rest };
    if (!data.git_provider_token) delete data.git_provider_token;

    // Build integration_config for Notion. Only include fields with values so
    // partial updates don't overwrite stored settings with blanks.
    if (form.task_source === "notion") {
      const cfg: Record<string, unknown> = {};
      if (notion.notion_database_id) cfg.notion_database_id = notion.notion_database_id;
      if (notion.notion_api_key) cfg.notion_api_key = notion.notion_api_key;
      if (notion.notion_status_property) cfg.notion_status_property = notion.notion_status_property;
      if (notion.notion_tag_property) cfg.notion_tag_property = notion.notion_tag_property;
      if (notion.notion_title_property) cfg.notion_title_property = notion.notion_title_property;
      if (Object.keys(cfg).length > 0) data.integration_config = cfg;
    }
    onSubmit(data);
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {!isEdit && (
        <div className="col-span-1 sm:col-span-2 flex flex-col gap-1">
          <span className="text-xs text-gray-400 inline-flex items-center gap-1"><Server className="w-3 h-3" />Workspace Servers (used to verify repo access)</span>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {servers.map((s) => (
              <label key={s.id} className="flex items-center gap-2 cursor-pointer py-1">
                <input
                  type="checkbox"
                  checked={(form.workspace_server_ids ?? []).includes(s.id)}
                  onChange={(e) => {
                    const ids = form.workspace_server_ids ?? [];
                    setForm((p) => ({
                      ...p,
                      workspace_server_ids: e.target.checked
                        ? [...ids, s.id]
                        : ids.filter((id) => id !== s.id),
                    }));
                  }}
                  className="accent-blue-500 w-3.5 h-3.5"
                />
                <span className="text-sm text-gray-300">{s.name}</span>
                <span className="text-xs text-gray-600">{s.hostname}</span>
              </label>
            ))}
          </div>
          {servers.length === 0 && (
            <p className="text-xs text-gray-600 italic">No workspace servers configured.</p>
          )}
          <div className="flex gap-2 mt-1">
            <button onClick={handleTestConn} title="Test SSH connection to first selected server" className="px-2 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 inline-flex items-center gap-1">
              <Zap className="w-4 h-4" />Test Connection
            </button>
          </div>
          {connStatus && <StatusLine s={connStatus} />}
        </div>
      )}

      {!isEdit && <UrlSection gitUrl={gitUrl} setGitUrl={setGitUrl} onParsed={handleParsed} workspaceServerId={form.workspace_server_ids[0] ?? null} />}

      <Field label="project_id" icon={Tag}>
        <input className={CLS} value={form.project_id} onChange={(e) => set("project_id", e.target.value)} disabled={isEdit} />
      </Field>
      <Field label="project_slug" icon={Tag}>
        <input className={CLS} value={form.project_slug} onChange={(e) => set("project_slug", e.target.value)} />
      </Field>
      <Field label="repo_owner" icon={Globe}>
        <input className={CLS} value={form.repo_owner} onChange={(e) => set("repo_owner", e.target.value)} />
      </Field>
      <Field label="repo_name" icon={Globe}>
        <input className={CLS} value={form.repo_name} onChange={(e) => set("repo_name", e.target.value)} />
      </Field>
      <Field label="default_branch" icon={GitBranch}>
        <input className={CLS} value={form.default_branch} onChange={(e) => set("default_branch", e.target.value)} />
      </Field>
      <Field label={providerHost ? `git_provider (${providerHost})` : "git_provider"} icon={Globe}>
        <select className={CLS} value={form.git_provider} onChange={(e) => set("git_provider", e.target.value)}>
          {GIT_PROVIDERS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </Field>
      <Field label="task_source">
        <select className={CLS} value={form.task_source} onChange={(e) => set("task_source", e.target.value)}>
          {TASK_SOURCES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </Field>
      <Field label={`Access Token${initial?.has_git_provider_token ? " (set)" : ""}`} icon={Key}>
        <input className={CLS} type="password" placeholder={initial?.has_git_provider_token ? "••••••• (leave blank to keep)" : "Per-project access token (optional)"} value={form.git_provider_token} onChange={(e) => set("git_provider_token", e.target.value)} />
      </Field>

      {form.task_source === "notion" && (
        <div
          className="col-span-1 sm:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-lg border border-gray-700/60 bg-gray-900/40"
          data-testid="notion-fields"
        >
          <div className="col-span-1 sm:col-span-2 text-xs text-gray-400 inline-flex items-center gap-1">
            <Key className="w-3 h-3" />Notion Integration
          </div>
          <Field label={`Notion API Key${hasNotionKey ? " (set)" : ""}`} icon={Key}>
            <input
              className={CLS}
              type="password"
              placeholder={hasNotionKey ? "••••••• (leave blank to keep)" : "secret_..."}
              value={form.notion.notion_api_key}
              onChange={(e) => setNotion("notion_api_key", e.target.value)}
            />
          </Field>
          <Field label="Notion Database ID" icon={Tag}>
            <input
              className={CLS}
              value={form.notion.notion_database_id}
              onChange={(e) => setNotion("notion_database_id", e.target.value)}
              placeholder="UUID of the database to watch"
            />
          </Field>
          <Field label="Title property">
            <input
              className={CLS}
              value={form.notion.notion_title_property}
              onChange={(e) => setNotion("notion_title_property", e.target.value)}
            />
          </Field>
          <Field label="Status property">
            <input
              className={CLS}
              value={form.notion.notion_status_property}
              onChange={(e) => setNotion("notion_status_property", e.target.value)}
            />
          </Field>
          <Field label="Tag property">
            <input
              className={CLS}
              value={form.notion.notion_tag_property}
              onChange={(e) => setNotion("notion_tag_property", e.target.value)}
            />
          </Field>
        </div>
      )}

      {POLL_CAPABLE_SOURCES.has(form.task_source) && (
        <div
          className="col-span-1 sm:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-lg border border-gray-700/60 bg-gray-900/40"
          data-testid="polling-fields"
        >
          <div className="col-span-1 sm:col-span-2 text-xs text-gray-400 inline-flex items-center gap-1">
            <Zap className="w-3 h-3" />Issue Polling (fallback to webhooks)
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={form.poll_enabled}
              onChange={(e) => set("poll_enabled", e.target.checked)}
              className="accent-blue-500 w-3.5 h-3.5"
            />
            Enable periodic issue polling
          </label>
          <Field label="Poll interval (minutes)">
            <input
              className={CLS}
              type="number"
              min={1}
              value={form.poll_interval_minutes}
              onChange={(e) =>
                set("poll_interval_minutes", Math.max(1, Number(e.target.value) || 5))
              }
            />
          </Field>
        </div>
      )}

      {isEdit && (
        <div className="col-span-1 sm:col-span-2 flex flex-col gap-1">
          <span className="text-xs text-gray-400 inline-flex items-center gap-1"><Server className="w-3 h-3" />workspace_servers</span>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {servers.map((s) => (
              <label key={s.id} className="flex items-center gap-2 cursor-pointer py-1">
                <input
                  type="checkbox"
                  checked={(form.workspace_server_ids ?? []).includes(s.id)}
                  onChange={(e) => {
                    const ids = form.workspace_server_ids ?? [];
                    setForm((p) => ({
                      ...p,
                      workspace_server_ids: e.target.checked
                        ? [...ids, s.id]
                        : ids.filter((id) => id !== s.id),
                    }));
                  }}
                  className="accent-blue-500 w-3.5 h-3.5"
                />
                <span className="text-sm text-gray-300">{s.name}</span>
                <span className="text-xs text-gray-600">{s.hostname}</span>
              </label>
            ))}
          </div>
          {servers.length === 0 && (
            <p className="text-xs text-gray-600 italic">No workspace servers configured.</p>
          )}
          <div className="flex gap-2 mt-1">
            <button onClick={handleTestConn} title="Test SSH connection to first selected server" className="px-2 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 inline-flex items-center gap-1">
              <Zap className="w-4 h-4" />Test Connection
            </button>
          </div>
          {connStatus && <StatusLine s={connStatus} />}
        </div>
      )}

      <div className="col-span-1 sm:col-span-2 flex flex-col gap-2 mt-2">
        {saveErr && <StatusLine s={{ ok: false, msg: saveErr }} />}
        <div className="flex gap-2">
          <button onClick={handleSave} className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm shadow-sm shadow-blue-900/30 focus:outline-none focus:ring-2 focus:ring-blue-500/40">Save</button>
          <button onClick={onCancel} className="px-4 py-1.5 text-gray-400 hover:text-white text-sm rounded-lg hover:bg-gray-700/50 transition-colors">Cancel</button>
        </div>
      </div>
    </div>
  );
}