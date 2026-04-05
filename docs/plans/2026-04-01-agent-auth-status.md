# Agent Auth Status & Login Flow

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show per-agent authentication status on workspace servers and allow one-click login via terminal popup.

**Architecture:** Extend the existing agent status check to also run `claude auth status --json` (and similar per-agent auth checks) via SSH. Add an "Authenticate" button that opens a terminal panel with the login command pre-launched, so the user can complete the OAuth flow.

**Tech Stack:** FastAPI, SSH, tmux, React, xterm.js (all existing in the project)

---

### Task 1: Add auth fields to backend schema

**Files:**
- Modify: `backend/schemas/agents.py` — `AgentInstallStatus` model

**Step 1: Add auth fields to AgentInstallStatus**

Add three fields to `AgentInstallStatus`:

```python
class AgentInstallStatus(BaseModel):
    agent_name: str
    display_name: str
    description: str
    agent_type: str  # cli_binary | api_service
    installed: bool
    version: str | None = None
    path: str | None = None
    # Auth status
    authenticated: bool | None = None
    auth_email: str | None = None
    auth_method: str | None = None
```

`authenticated` is `None` when auth check is not applicable (e.g., API-based agents like Ollama that don't need auth).

**Step 2: Commit**

```bash
git add backend/schemas/agents.py
git commit -m "feat: add auth fields to AgentInstallStatus schema"
```

---

### Task 2: Add auth check to AgentInstallService

**Files:**
- Modify: `backend/services/workspace/agent_install_service.py`

**Step 1: Add auth check method**

Add a method `check_agent_auth` that runs auth status commands per agent via SSH:

```python
# Map agent names to their auth check commands
_AUTH_CHECK_COMMANDS: dict[str, str] = {
    "claude": "claude auth status --json",
}

async def check_agent_auth(
    self, agent_name: str, as_user: str | None = None,
) -> dict[str, str | bool | None]:
    """Check authentication status for an agent. Returns dict with
    authenticated (bool|None), auth_email (str|None), auth_method (str|None).
    """
    cmd = _AUTH_CHECK_COMMANDS.get(agent_name)
    if not cmd:
        return {"authenticated": None, "auth_email": None, "auth_method": None}

    wrapped = _wrap_as_user(cmd, as_user) if as_user else cmd
    try:
        stdout, _stderr, rc = await self._ssh.run_command(wrapped, timeout=15)
        if rc != 0:
            return {"authenticated": False, "auth_email": None, "auth_method": None}
        import json as _json
        data = _json.loads(stdout.strip())
        return {
            "authenticated": data.get("loggedIn", False),
            "auth_email": data.get("email"),
            "auth_method": data.get("authMethod"),
        }
    except Exception:
        return {"authenticated": None, "auth_email": None, "auth_method": None}
```

**Step 2: Integrate into check_all_agents**

After building each `AgentStatus`, also run `check_agent_auth` for installed agents and attach the results. Modify the `AgentStatus` dataclass to include auth fields:

```python
@dataclass
class AgentStatus:
    agent_name: str
    display_name: str
    description: str
    agent_type: str
    installed: bool
    version: str | None = None
    path: str | None = None
    authenticated: bool | None = None
    auth_email: str | None = None
    auth_method: str | None = None
```

In `check_all_agents`, after discovery, run auth checks for installed agents:

```python
# After building results list, enrich with auth status
for r in results:
    if r.installed:
        auth = await self.check_agent_auth(r.agent_name, as_user=as_user)
        r.authenticated = auth["authenticated"]
        r.auth_email = auth["auth_email"]
        r.auth_method = auth["auth_method"]
```

**Step 3: Commit**

```bash
git add backend/services/workspace/agent_install_service.py
git commit -m "feat: add agent auth status checking via SSH"
```

---

### Task 3: Update agent status API endpoint

**Files:**
- Modify: `backend/api/servers/agent_management.py`

**Step 1: Pass auth fields through to response**

In `get_agent_status`, the `AgentInstallStatus` construction already maps from `AgentStatus` dataclass. Add the new fields:

```python
agent_statuses = [
    AgentInstallStatus(
        agent_name=a.agent_name,
        display_name=a.display_name,
        description=a.description,
        agent_type=a.agent_type,
        installed=a.installed,
        version=a.version,
        path=a.path,
        authenticated=a.authenticated,
        auth_email=a.auth_email,
        auth_method=a.auth_method,
    )
    for a in worker_agents
]
```

**Step 2: Add auth-login endpoint**

Add a new endpoint that starts `claude auth login` in a tmux session on the workspace server and returns the tmux session name so the frontend can attach a terminal to it:

```python
@router.post("/workspace-servers/{server_id}/agents/{agent_name}/auth-login")
async def start_agent_auth_login(
    server_id: int,
    agent_name: str,
    repo: WorkspaceServerRepository = Depends(_get_repo),
):
    """Start an interactive auth login flow for an agent in a tmux session."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    # Only Claude supported for now
    login_commands = {
        "claude": "claude auth login --claudeai",
    }
    login_cmd = login_commands.get(agent_name)
    if not login_cmd:
        raise HTTPException(400, f"Agent '{agent_name}' does not support interactive auth login")

    username = server.worker_user or "coder"
    ssh = SSHService.for_server(server)

    # Create a tmux session for the auth flow
    tmux_name = f"auth-{agent_name}-{server_id}"

    # Kill any existing auth session first
    kill_cmd = f"tmux kill-session -t {shlex.quote(tmux_name)} 2>/dev/null || true"
    await ssh.run_command(kill_cmd, timeout=5)

    # Create new tmux session running the login command as worker user
    home = f"/home/{username}"
    user_path = (
        f"{home}/.local/bin:{home}/.claude/bin"
        ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )
    inner_cmd = (
        f"export HOME={home} && "
        f"export PATH={shlex.quote(user_path)} && "
        f"{login_cmd}"
    )
    wrapped = f"runuser -l {shlex.quote(username)} -c {shlex.quote(inner_cmd)}"
    create_cmd = (
        f"tmux new-session -d -s {shlex.quote(tmux_name)} "
        f"-x 200 -y 50 "
        f"{shlex.quote(wrapped)}"
    )
    await ssh.run_command(create_cmd, timeout=10)

    return {
        "tmux_session": tmux_name,
        "server_id": server_id,
        "agent_name": agent_name,
    }
```

**Step 3: Commit**

```bash
git add backend/api/servers/agent_management.py
git commit -m "feat: add agent auth login endpoint with tmux session"
```

---

### Task 4: Add WebSocket endpoint for auth terminal

**Files:**
- Modify: `backend/api/ws.py`

**Step 1: Add auth terminal WebSocket**

Add a WebSocket endpoint that attaches to the auth tmux session:

```python
@router.websocket("/ws/servers/{server_id}/auth-terminal/{tmux_name}")
async def ws_auth_terminal(websocket: WebSocket, server_id: int, tmux_name: str):
    """Attach to an auth login tmux session on a workspace server."""
    await websocket.accept()
    async with async_session() as db:
        server = (await db.execute(
            select(WorkspaceServer).where(WorkspaceServer.id == server_id)
        )).scalar_one_or_none()
    if not server:
        await websocket.close(code=1008, reason="Server not found")
        return

    ssh = SSHService.for_server(server)
    conn = await ssh._connect()
    try:
        process = await conn.create_process(
            f"tmux attach-session -t {shlex.quote(tmux_name)}",
            term_type="xterm-256color",
            term_size=(200, 50),
        )

        async def ssh_to_ws():
            try:
                while not process.stdout.at_eof():
                    data = await process.stdout.read(4096)
                    if data:
                        await websocket.send_text(
                            json.dumps({"type": "output", "data": data})
                        )
            except (asyncssh.BreakReceived, asyncssh.SignalReceived):
                pass

        async def ws_to_ssh():
            try:
                while True:
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)
                    if msg.get("type") == "input":
                        process.stdin.write(msg["data"])
                    elif msg.get("type") == "resize":
                        process.change_terminal_size(
                            msg.get("cols", 200), msg.get("rows", 50)
                        )
            except WebSocketDisconnect:
                pass

        done, pending = await asyncio.wait(
            [asyncio.ensure_future(ssh_to_ws()), asyncio.ensure_future(ws_to_ssh())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        conn.close()
```

Note: This follows the exact same pattern as the existing `/ws/servers/{server_id}/terminal` endpoint in `ws.py`. Deduplicate later if needed.

**Step 2: Commit**

```bash
git add backend/api/ws.py
git commit -m "feat: add WebSocket endpoint for agent auth terminal"
```

---

### Task 5: Update frontend types and API

**Files:**
- Modify: `frontend/src/types/agents.ts`
- Modify: `frontend/src/api/agents.ts`

**Step 1: Add auth fields to AgentInstallStatus type**

```typescript
export interface AgentInstallStatus {
  agent_name: string;
  display_name: string;
  description: string;
  agent_type: string;
  installed: boolean;
  version: string | null;
  path: string | null;
  authenticated: boolean | null;
  auth_email: string | null;
  auth_method: string | null;
}
```

**Step 2: Add auth login API function**

In `frontend/src/api/agents.ts`, add:

```typescript
export const startAgentAuthLogin = (serverId: number, agentName: string) =>
  post<{ tmux_session: string; server_id: number; agent_name: string }>(
    `/workspace-servers/${serverId}/agents/${encodeURIComponent(agentName)}/auth-login`,
  );
```

**Step 3: Commit**

```bash
git add frontend/src/types/agents.ts frontend/src/api/agents.ts
git commit -m "feat: add auth status types and auth login API"
```

---

### Task 6: Update AgentManagementPanel UI

**Files:**
- Modify: `frontend/src/components/servers/AgentManagementPanel.tsx`

**Step 1: Add AuthBadge component**

```typescript
function AuthBadge({ status, email }: { status: boolean | null; email: string | null }) {
  if (status === null) return null; // not applicable for this agent
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${
        status
          ? "bg-blue-500/10 text-blue-400 border border-blue-800/40"
          : "bg-amber-500/10 text-amber-400 border border-amber-800/40"
      }`}
      title={status && email ? `Authenticated as ${email}` : "Not authenticated"}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${status ? "bg-blue-400" : "bg-amber-400"}`} />
      {status ? "Authenticated" : "Not Authenticated"}
    </span>
  );
}
```

**Step 2: Add AuthTerminalModal component**

A modal that embeds an xterm.js terminal connected to the auth tmux session:

```typescript
function AuthTerminalModal({
  serverId,
  tmuxName,
  agentName,
  onClose,
  onComplete,
}: {
  serverId: number;
  tmuxName: string;
  agentName: string;
  onClose: () => void;
  onComplete: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: "ui-monospace, Menlo, Monaco, 'Cascadia Code', monospace",
      theme: {
        background: "#0d1117",
        foreground: "#c9d1d9",
        cursor: "#58a6ff",
        selectionBackground: "#264f78",
      },
    });
    termRef.current = term;
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon());
    term.open(el);
    fitAddon.fit();

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${proto}//${window.location.host}/ws/servers/${serverId}/auth-terminal/${encodeURIComponent(tmuxName)}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "output") term.write(msg.data);
    };
    term.onData((data) => ws.send(JSON.stringify({ type: "input", data })));

    const resizeObs = new ResizeObserver(() => {
      fitAddon.fit();
      ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    });
    resizeObs.observe(el);

    return () => {
      resizeObs.disconnect();
      ws.close();
      term.dispose();
    };
  }, [serverId, tmuxName]);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-5 w-full max-w-2xl mx-4 shadow-2xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-white">
            Authenticate {agentName} — complete the login flow below
          </h3>
          <button onClick={() => { onComplete(); onClose(); }}
            className="text-gray-400 hover:text-white p-1 rounded hover:bg-gray-700/50">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-xs text-gray-400 mb-3">
          Click the link shown below, sign in with your browser, then paste the code back here.
        </p>
        <div ref={containerRef} className="h-72 rounded-lg overflow-hidden border border-gray-800" />
        <div className="flex justify-end mt-3 gap-2">
          <button onClick={() => { onComplete(); onClose(); }}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm transition-colors">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 3: Update AgentRow to show auth badge + authenticate button**

Add auth badge next to the install status badge. Add an "Authenticate" button for installed but unauthenticated agents:

```typescript
function AgentRow({
  agent,
  onInstall,
  onAuthenticate,
  installing,
}: {
  agent: AgentInstallStatus;
  onInstall: (name: string, reinstall?: boolean) => void;
  onAuthenticate: (name: string) => void;
  installing: string | null;
}) {
  const isInstalling = installing === agent.agent_name;

  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-800/30 transition-colors">
      <div className="flex items-center gap-3 min-w-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">{agent.display_name}</span>
            <span className="text-xs text-gray-500 font-mono">{agent.agent_name}</span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{agent.description}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-4">
        {agent.installed && agent.version && (
          <span className="text-xs text-gray-500 font-mono">{agent.version}</span>
        )}
        <StatusBadge installed={agent.installed} />
        {agent.installed && <AuthBadge status={agent.authenticated} email={agent.auth_email} />}
        {/* Authenticate button for installed but not authenticated agents */}
        {agent.installed && agent.authenticated === false && (
          <button
            onClick={() => onAuthenticate(agent.agent_name)}
            className="text-xs px-2 py-1 bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-700/40 rounded transition-colors inline-flex items-center gap-1"
          >
            <LogIn className="w-3 h-3" />
            Authenticate
          </button>
        )}
        {/* existing install/reinstall buttons unchanged */}
        {agent.installed ? (
          <button onClick={() => onInstall(agent.agent_name, true)} ...>Reinstall</button>
        ) : (
          <button onClick={() => onInstall(agent.agent_name)} ...>Install</button>
        )}
      </div>
    </div>
  );
}
```

**Step 4: Wire up the auth flow in the parent component**

In `AgentManagementPanel`:

```typescript
const [authModal, setAuthModal] = useState<{
  tmuxName: string;
  agentName: string;
} | null>(null);

const handleAuthenticate = async (agentName: string) => {
  try {
    const result = await startAgentAuthLogin(serverId, agentName);
    setAuthModal({ tmuxName: result.tmux_session, agentName });
  } catch {
    setError(`Failed to start auth flow for ${agentName}`);
  }
};

// In the render, pass onAuthenticate to AgentRow
// After the install dialog, add the auth terminal modal:
{authModal && (
  <AuthTerminalModal
    serverId={serverId}
    tmuxName={authModal.tmuxName}
    agentName={authModal.agentName}
    onClose={() => setAuthModal(null)}
    onComplete={() => load()}
  />
)}
```

**Step 5: Add LogIn import**

```typescript
import { Download, Loader2, LogIn, RefreshCw, RotateCcw, X } from "lucide-react";
```

And add xterm imports:

```typescript
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
```

**Step 6: Commit**

```bash
git add frontend/src/components/servers/AgentManagementPanel.tsx
git commit -m "feat: add auth status badges and authenticate terminal modal"
```

---

### Task 7: Verify end-to-end

**Step 1: Rebuild and test**

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

**Step 2: Test the flow**

1. Navigate to Workspace Servers page
2. Expand a server's agent panel
3. Verify auth status badges show for Claude (Authenticated/Not Authenticated)
4. If not authenticated, click "Authenticate" button
5. Verify terminal modal opens with `claude auth login --claudeai`
6. Complete the login flow (visit URL, paste code)
7. Close modal, verify badge updates to "Authenticated"

**Step 3: Run lints**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/schemas/agents.py backend/services/workspace/agent_install_service.py backend/api/servers/agent_management.py backend/api/ws.py --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/schemas/agents.py backend/services/workspace/agent_install_service.py backend/api/servers/agent_management.py backend/api/ws.py
docker compose -f docker-compose.dev.yml exec frontend npx eslint src/components/servers/AgentManagementPanel.tsx src/types/agents.ts src/api/agents.ts --fix
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: agent auth status checking and interactive login flow"
```
