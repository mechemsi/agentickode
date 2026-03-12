# AutoDev Worker Pipeline — Complete Technical Reference

This document covers every detail of the worker pipeline: engine polling, phase sequencing, prompt templates, SSH commands, timeouts, retry logic, and data flow.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Worker Engine](#worker-engine)
3. [Pipeline Sequencer](#pipeline-sequencer)
4. [Phase 0: Workspace Setup](#phase-0-workspace-setup)
5. [Phase 1: Init](#phase-1-init)
6. [Phase 2: Planning](#phase-2-planning)
7. [Phase 3: Coding](#phase-3-coding)
8. [Phase 4: Testing](#phase-4-testing)
9. [Phase 5: Reviewing](#phase-5-reviewing)
10. [Phase 6: Approval](#phase-6-approval)
11. [Phase 7: Finalization](#phase-7-finalization)
12. [Optional: PR Fetch Phase](#optional-pr-fetch-phase)
13. [Optional: Task Creation Phase](#optional-task-creation-phase)
14. [CLI Adapter](#cli-adapter)
15. [Broadcaster](#broadcaster)
16. [Helper Functions](#helper-functions)
17. [Timeout & Limit Reference](#timeout--limit-reference)
18. [Workflow Templates](#workflow-templates)
19. [Data Flow Diagram](#data-flow-diagram)

---

## Architecture Overview

```
FastAPI lifespan
  └── WorkerEngine.run()          # Polling loop (every 2s)
        ├── _dispatch_pending()    # Pick up pending TaskRuns
        ├── _handle_waiting()     # Resume approved/triggered runs
        └── _handle_timeouts()    # Timeout stale approval waits

execute_pipeline(run, session, services)
  └── Phase loop (PhaseExecution rows):
        workspace_setup → init → planning → coding → testing → reviewing → approval → finalization
```

**Key components:**

| Component | File | Purpose |
|-----------|------|---------|
| `WorkerEngine` | `backend/worker/engine.py` | Polling loop, task dispatch, approval handling |
| `execute_pipeline()` | `backend/worker/pipeline.py` | Phase sequencer with retry and trigger logic |
| `Broadcaster` | `backend/worker/broadcaster.py` | Log persistence (DB) + WebSocket fan-out |
| `CLIAdapter` | `backend/services/adapters/cli_adapter.py` | SSH-based CLI agent execution |
| `ServiceContainer` | `backend/services/container.py` | DI container passed to all phases |
| Phase modules | `backend/worker/phases/*.py` | Individual phase implementations |

**ServiceContainer contents:**
```python
@dataclass
class ServiceContainer:
    ollama: OllamaService
    openhands: OpenHandsService
    chromadb: ChromaDBService
    role_resolver: RoleResolver
    task_source_updater: TaskSourceUpdater | None = None
    webhook_callbacks: WebhookCallbackService | None = None
```

---

## Worker Engine

**File:** `backend/worker/engine.py`

### Polling Loop

```python
async def run(self):
    self._running = True
    while self._running:
        await self._tick()
        await asyncio.sleep(settings.poll_interval_seconds)  # Default: 2 seconds
```

- **Poll interval:** `settings.poll_interval_seconds` = **2 seconds**
- **Max concurrent runs:** `settings.max_concurrent_runs` = **3**
- **Approval timeout:** `settings.approval_timeout_hours` = **24 hours**

### Tick Operations

Each tick performs 3 operations in sequence:

#### 1. Cleanup (`_tick`)
```
Remove completed/failed asyncio.Tasks from self._active_runs dict
Log exceptions from failed tasks
```

#### 2. Dispatch Pending (`_dispatch_pending`)
```
Calculate: available_slots = max_concurrent_runs - len(active_runs)
If no slots → return immediately

Query DB:
  SELECT * FROM task_runs
  WHERE status = 'pending'
    AND project_id NOT IN (
      SELECT DISTINCT project_id FROM task_runs WHERE status IN ('running', 'waiting_for_trigger')
    )
  ORDER BY created_at
  LIMIT available_slots

Constraint: Only 1 run dispatched per project per tick (prevents racing)

For each qualifying run:
  asyncio.create_task(_run_pipeline(run.id))
  Store in self._active_runs[run.id]
```

#### 3. Handle Waiting (`_handle_waiting`)

**Approval handling:**
```
Query: status = 'awaiting_approval' AND approved IS NOT NULL

If run.approved == True:
  - Find PhaseExecution with status='waiting' and trigger_mode='wait_for_approval'
  - Set phase status to 'completed'
  - Set run status to 'pending'
  - Create asyncio.Task to resume pipeline

If run.approved == False:
  - Find PhaseExecution with status='waiting'
  - Set phase status to 'failed', error = "Rejected: {reason}"
  - Set run status to 'failed'
  - Broadcast 'run_rejected' event
```

**External trigger handling:**
```
Query: status = 'waiting_for_trigger'

For each:
  - Check if any PhaseExecution has status='pending' (externally advanced)
  - If yes: set run status to 'pending', resume pipeline
```

#### 4. Handle Timeouts (`_handle_timeouts`)
```
cutoff = now - 24 hours

Query: status = 'awaiting_approval'
       AND approved IS NULL
       AND approval_requested_at < cutoff

For each: set status = 'timeout', error = "Approval timeout after 24h"
Broadcast 'run_timeout' event
```

### Pipeline Execution Wrapper

```python
async def _run_pipeline(self, run_id):
    async with async_session() as session:
        run = await session.get(TaskRun, run_id)
        if not run or run.status != "pending":
            return
        try:
            await execute_pipeline(run, session, self._get_services())
        except Exception:
            run.status = "failed"
            run.error_message = "Unhandled pipeline error"
            run.completed_at = datetime.now(UTC)
            await session.commit()
```

---

## Pipeline Sequencer

**File:** `backend/worker/pipeline.py`

### Default Phase Sequence

```python
PHASE_NAMES = [
    "workspace_setup",    # Phase 0
    "init",               # Phase 1
    "planning",           # Phase 2
    "coding",             # Phase 3
    "testing",            # Phase 4
    "reviewing",          # Phase 5
    "approval",           # Phase 6
    "finalization",       # Phase 7
]
```

### Phase Module Mapping

```python
_PHASE_MODULE_MAP = {
    "workspace_setup": "workspace_setup",
    "init":            "init_phase",
    "planning":        "planning",
    "coding":          "coding",
    "testing":         "testing",
    "reviewing":       "reviewing",
    "approval":        "approval",
    "finalization":    "finalization",
    "task_creation":   "task_creation",
    "pr_fetch":        "pr_fetch",
}
```

### Workflow Resolution Priority

```
1. Explicit run.workflow_template_id → look up WorkflowTemplate by ID
2. Label-based matching → run.task_source_meta.labels → WorkflowTemplateRepository.match_labels()
3. Default template → WorkflowTemplateRepository.get_default()
4. Hardcoded fallback → PHASE_NAMES list above
```

Only enabled phases (`p.get("enabled", True)`) are included.

### Phase Execution Loop

```
execute_pipeline(run, session, services):

1. Set run.status = "running", run.started_at = now
   Broadcast event: "run_started"

2. Create PhaseExecution rows (if not existing) from resolved workflow

3. WHILE True:
   a. Get next pending PhaseExecution (ordered by order_index)
      If none → break (all phases done)

   b. Skip unknown phases (set to "skipped")

   c. Check for external cancellation:
      Refresh run from DB → if status == "cancelled" → return

   d. PRE-execute trigger_mode check:
      If trigger_mode == "wait_for_trigger":
        - Set phase status to "waiting"
        - Set run status to "waiting_for_trigger"
        - Broadcast log + event
        - RETURN (pipeline pauses)

   e. Execute the phase:
      - Set run.current_phase, run.phase_started_at
      - Set phase status to "running"
      - Broadcast event: "phase_changed"
      - Call: phase_mod.run(run, session, services, phase_config=phase_exec.phase_config)

   f. ON EXCEPTION:
      - Increment phase_exec.retry_count
      - If retry_count < max_retries:
          Log warning with retry count
          Reset phase status to "pending"
          CONTINUE loop (retry)
      - If retries exhausted:
          Set phase status to "failed"
          Set run.status = "failed"
          Set run.error_message = "{phase_name}: {error_msg}"
          Broadcast events: "phase_failed", "run_failed"
          Notify task source (if configured)
          Fire webhook callbacks (if configured)
          RETURN

   g. ON SUCCESS:
      - Set phase status to "completed"
      - Update legacy JSONB columns (backward compat):
          workspace_setup → run.workspace_result
          planning        → run.planning_result
          coding          → run.coding_results
          testing         → run.test_results
          reviewing       → run.review_result
      - Broadcast log + event: "phase_completed"
      - Notify task source (if configured)
      - Fire webhook callbacks (if configured)

   h. POST-execute trigger_mode check:
      If trigger_mode == "wait_for_approval":
        - Set phase status to "waiting"
        - Set run.status = "awaiting_approval"
        - Set run.approval_requested_at = now
        - Broadcast log + event
        - RETURN (pipeline pauses)

4. All phases complete:
   Set run.status = "completed", run.completed_at = now
   Broadcast log + event: "run_completed"
   Fire webhook callbacks
```

### PhaseExecution Status Lifecycle

```
pending → running → completed
                  → failed
                  → waiting (paused for approval/trigger)
                  → skipped (unknown phase)
```

### Retry Logic

- Each `PhaseExecution` has its own `retry_count` and `max_retries`
- On exception: `retry_count += 1`
- If `retry_count < max_retries`: reset to "pending", loop continues
- If exhausted: phase fails, run fails, pipeline returns
- `SSHCommandError` exceptions produce user-friendly messages

---

## Phase 0: Workspace Setup

**File:** `backend/worker/phases/workspace_setup.py`
**Purpose:** Clone, scaffold, or cluster repositories on the remote workspace server

### Phase Signature

```python
async def run(task_run, session, services, phase_config=None) -> None
```

### Workspace Types

#### Type: "existing" (default)

```
1. Connect via SSH to workspace server
2. Check if git repo exists at task_run.workspace_path
   Command: RemoteGitOps.has_repo(workspace) → runs "git status" via SSH
3. If repo exists:
   Command: git pull origin {default_branch}
4. If repo does not exist:
   a. Create directory: mkdir -p {workspace}
   b. Resolve repo URL from:
      - workspace_config.repos[0].url
      - OR construct from repo_owner/repo_name + git_provider
   c. Resolve auth URL (SSH-first, HTTPS-token fallback)
   d. Command: git clone {auth_url} {workspace} --branch {branch}
```

#### Type: "new"

```
1. Create directory: mkdir -p {workspace}
2. Command: git init
3. Command: git checkout -b {default_branch}
4. If scaffold_template specified:
   Command: bash /opt/autodev/docker/sandboxes/{template}/scaffold.sh
   Timeout: 300 seconds
5. Command: git add -A
6. Command: git commit -m "Initial project scaffold" --allow-empty
7. If repo_owner+repo_name specified:
   a. Create remote repo via GitProvider.create_repo()
   b. Command: git remote add origin {auth_url}
   c. Command: git push -u origin {default_branch}
```

#### Type: "cluster"

```
1. Create base directory: mkdir -p {workspace}
2. For each repo in workspace_config.repos:
   a. Resolve auth URL
   b. Determine destination: {workspace}/{dir_name}
   c. Command: git clone or git pull (clone_or_pull)
3. If sandbox config specified:
   Start Docker sandbox container with:
   - template
   - mount_points
   - env_vars
   - http_port (default: 8080)
```

### Auth URL Resolution

```python
get_auth_url(repo_url, git_provider, ssh):
  1. Check SSH key availability via GitAccessService.get_public_key()
  2. If SSH key available: convert to SSH URL (git@host:owner/repo.git)
  3. Otherwise: inject HTTPS token credentials into URL
  Returns: (authenticated_url, method="ssh"|"https")
```

### Output

```python
task_run.workspace_result = {
    "workspace_path": "/workspaces/project-name",
    "repos_cloned": ["/workspaces/project-name"]
}
```

---

## Phase 1: Init

**File:** `backend/worker/phases/init_phase.py`
**Purpose:** Create feature branch + retrieve project context from ChromaDB

### Flow

```
1. Connect via SSH to workspace server
2. Branch handling:
   a. If task_source_meta.pr_head_branch exists (fix-pr workflow):
      Command: git checkout {pr_branch}
      Command: git pull origin {pr_branch}
      Set: task_run.branch_name = pr_branch
   b. Otherwise (normal flow):
      Command: git checkout -b {branch_name}
      If branch already exists (RuntimeError):
        Command: git checkout {branch_name}

3. ChromaDB context retrieval:
   Call: services.chromadb.query_project_context(
       project_id,
       [task_run.title, task_run.description],
   )
   Returns: list[str] of context documents (gracefully returns [] on failure)

4. Store context for next phase:
   task_run.planning_result = {"context_docs": context_docs}
```

### Git Commands Executed

| Command | Purpose | Timeout |
|---------|---------|---------|
| `git checkout {pr_branch}` | Switch to PR branch (fix-pr) | Default SSH |
| `git pull origin {pr_branch}` | Update PR branch | Default SSH |
| `git checkout -b {branch_name}` | Create new feature branch | Default SSH |
| `git checkout {branch_name}` | Switch to existing branch (fallback) | Default SSH |

---

## Phase 2: Planning

**File:** `backend/worker/phases/planning.py`
**Purpose:** Decompose task into subtasks via LLM agent

### Role Resolution

```python
role = get_phase_role("planning", phase_config)  # Default: "planner"
resolved = await services.role_resolver.resolve(role, session, workspace_server_id)
adapter = resolved.adapter   # CLIAdapter or OllamaAdapter
config = resolved.agent_config  # AgentConfig with prompts, temperature, etc.
```

### System Prompt (Fallback)

```
You are a senior software architect specializing in task decomposition.

You analyze tasks and break them down into specific, implementable subtasks
ordered by dependency.
```

### User Prompt Template (Fallback)

```
## Task
Title: {title}
Description: {description}

## Project Context
{context_text}

## Instructions
1. Analyze the task requirements
2. Break down into specific, implementable subtasks
3. Order subtasks by dependency (what must be done first)
4. Estimate complexity (simple/medium/complex)

Respond in JSON format:
{
  "subtasks": [
    {"id": 1, "title": "...", "description": "...", "files_likely_affected": ["..."]}
  ],
  "estimated_complexity": "simple|medium|complex",
  "notes": "Any important considerations"
}
```

### Agent Invocation

```python
response_text = await adapter.generate(
    user_prompt,
    system_prompt=system_prompt,
    temperature=0.3,         # Default from config
    num_predict=2048,        # Default from config
    log_fn=_log_ssh,         # Broadcasts SSH debug output
)
```

### Response Parsing

```python
plan_data = extract_json(response_text)  # Extracts first JSON block from response
subtasks = plan_data.get("subtasks", [])
complexity = plan_data.get("estimated_complexity", "medium")
```

### Output

```python
task_run.planning_result = {
    "subtasks": [
        {"id": 1, "title": "...", "description": "...", "files_likely_affected": ["..."]}
    ],
    "estimated_complexity": "simple|medium|complex",
    "context_used": [doc[:100] for doc in context_docs],  # Truncated previews
}
```

### Logs Emitted

1. `"Sending task to planner via {provider_name}"` — with system_prompt metadata
2. `"Task: {title}"` (debug) — with user prompt metadata
3. `"Received response ({N} chars) in {time}, parsing JSON"` — with response metadata
4. `"Subtask {i}: {title}"` (debug) — for each subtask
5. `"Planning complete: {N} subtasks, complexity={X}"`

---

## Phase 3: Coding

**File:** `backend/worker/phases/coding.py`
**Purpose:** Execute subtasks via CLI agent (Claude, codex, aider, etc.)

### Subtask Sources (Priority Order)

```
1. task_run.planning_result.subtasks (from planning phase)
2. PR review comments → synthesized into a subtask (fix-pr workflow)
3. task_run.title/description → synthesized single subtask (hotfix/small-task)
4. No subtasks → return empty results
```

### PR Comment Formatting

```python
def _format_pr_comments(comments):
    For each comment:
      - Extract body, path, line number
      - Format as: "- `path:line` comment_body"
    Returns: newline-joined string
```

### Agent Readiness Check

```python
await ensure_agent_ready(adapter, log_fn=_phase_log)
```

This call (detailed in [Helper Functions](#helper-functions)):
1. Checks if agent binary exists on server
2. Auto-installs if missing
3. Sets up non-root worker user (for Claude)
4. Copies binary to worker user's PATH if needed

### System Prompt (Fallback)

```
You are an expert software developer implementing code changes.

Follow existing code patterns and style. Add appropriate error handling.
Write or update tests if applicable. Commit changes with descriptive messages.
```

### User Prompt Template (Fallback)

```
## Subtask
{title}

## Description
{description}

## Files Likely Affected
{files}

## Previous Changes in This Session
{prev}

## Instructions
1. Implement the subtask as described
2. Follow existing code patterns and style
3. Add appropriate error handling
4. Write or update tests if applicable
5. Commit changes with a descriptive message
```

### Subtask Execution Loop

```
For each subtask (i = 0..N-1):
  1. Log: "Subtask {i+1}/{N}: {title}"
  2. Build coding prompt from template:
     - title, description from subtask
     - files = comma-joined files_likely_affected
     - prev = newline-joined previous_changes (from earlier subtasks)
  3. Log prompt metadata (debug)
  4. Log: "Running agent ({provider}) — this may take a few minutes"

  5. Execute agent:
     result = await adapter.run_task(
         workspace=task_run.workspace_path,
         instruction=coding_prompt,
         system_prompt=system_prompt,
         max_iterations=20,
         log_fn=_log_ssh,
     )
     Timeout: 600 seconds (10 minutes)

  6. Extract result fields:
     - files_changed: list[str]
     - exit_code: int
     - output: str (agent stdout)
     - stderr: str

  7. Log response metadata (debug)

  8. Check for agent not found:
     If exit_code == 127 → raise RuntimeError (fatal)

  9. Track failures:
     If exit_code != 0 → failed_count += 1, log error

  10. Append to coding_results list
  11. Extend previous_changes with files_changed
  12. Log: "Done in {time} (exit={code}, files: {list})"
```

### Failure Conditions

```
- ALL subtasks failed (failed_count == len(subtasks)):
    → RuntimeError: "All {N} subtask(s) failed"

- No files changed across ALL subtasks (previous_changes is empty):
    → RuntimeError: "Coding produced no file changes across {N} subtask(s)"

- Agent not found (exit_code == 127):
    → RuntimeError: "Agent not available on server"
```

### Output

```python
task_run.coding_results = {
    "results": [
        {
            "subtask_title": "Implement user auth",
            "files_changed": ["auth.py", "models.py"],
            "exit_code": 0,
        },
        # ... one entry per subtask
    ]
}
```

---

## Phase 4: Testing

**File:** `backend/worker/phases/testing.py`
**Purpose:** Run tests on remote workspace server (best-effort, never fatal)

### Flow

```
1. Connect via SSH
2. Build test command:
   test_cmd = "cd {workspace} && make test"
3. Execute:
   stdout, stderr, rc = await ssh.run_command(test_cmd, timeout=300)
   Timeout: 300 seconds (5 minutes)
4. On ANY exception (e.g. no Makefile, no test runner):
   Return: {"success": True, "output": "No test runner found, skipped", "error": ""}
```

### Output Truncation

```
stdout: last 2000 characters
stderr: last 1000 characters
```

### Output

```python
task_run.test_results = {
    "success": True|False,   # rc == 0
    "output": "...",          # Truncated stdout
    "error": "...",           # Truncated stderr
}
```

### Key Behavior

- **Best-effort:** Testing phase NEVER fails the pipeline. Even if `make test` returns non-zero, the phase itself completes successfully. The test results are stored for informational purposes only.
- **Exception swallowing:** Any exception (SSH timeout, command not found, etc.) is caught and treated as "skipped".

---

## Phase 5: Reviewing

**File:** `backend/worker/phases/reviewing.py`
**Purpose:** AI code review with auto-fix retry loop

### Role Resolution

```python
role = get_phase_role("reviewing", phase_config)  # Default: "reviewer"
```

### System Prompt (Fallback)

```
You are a senior code reviewer. Review changes for correctness, quality,
error handling, security, and performance.
```

### User Prompt Template (Fallback)

```
## Task Context
Title: {title}
Description: {description}

## Files Changed
{files_changed}

## Diff
```diff
{diff_text}
```

## Review Criteria
1. Code correctness - does it implement the requirement?
2. Code quality - is it readable, maintainable?
3. Error handling - are edge cases covered?
4. Security - any vulnerabilities introduced?
5. Performance - any obvious inefficiencies?

Respond in JSON format:
{
  "approved": true,
  "issues": [
    {"severity": "critical|major|minor", "file": "...", "line": 0, "description": "..."}
  ],
  "suggestions": ["..."]
}
```

### Diff Source Resolution

```
1. Pre-fetched PR diff (from pr_fetch phase): coding_data.get("pr_diff")
   → Used directly, no SSH needed
2. SSH git diff (fallback):
   Command: git diff {default_branch}...{branch_name}
   → Executed via RemoteGitOps
   → On error: diff_text = "(diff unavailable)"
```

### Diff Truncation

```
diff_text[:10000]  — max 10,000 characters sent to reviewer
```

### Review Loop

```
retry_count = 0
max_retries = task_run.max_retries  (default: 3)

WHILE retry_count <= max_retries:
  1. Log: "Review attempt {attempt}/{max_retries + 1}"

  2. Get diff (pre-fetched or SSH)

  3. Build review prompt from template

  4. Call reviewer agent:
     response_text = await reviewer.generate(
         prompt,
         system_prompt=system_prompt,
         temperature=0.2,       # Lower = stricter reviews
         num_predict=2048,
         log_fn=_log_ssh,
     )

  5. Parse JSON response:
     Try: extract_json(response_text)
     On ValueError (parse failure):
       review_data = {
           "approved": False,
           "issues": [{"description": "Failed to parse review"}],
           "suggestions": [],
       }

  6. Extract: approved, issues, suggestions

  7. Critical issue override:
     critical = [i for i in issues if i.severity == "critical"]
     If any critical issues → approved = False (regardless of LLM output)

  8. Store review result:
     task_run.review_result = {"approved": approved, "issues": issues, "suggestions": suggestions}

  9. If approved:
     Log: "Review passed ({N} minor issues, {N} suggestions)"
     RETURN (phase complete)

  10. Log: "Review found {N} issues ({N} critical)"

  11. If no critical issues OR retries exhausted:
     BREAK (proceed anyway)

  12. Attempt auto-fix:
     a. Increment retry_count, store in task_run.retry_count
     b. Log: "Attempting auto-fix (retry {count}/{max})"
     c. Build fix instruction from critical issues:
        fix_instruction = "## Fix Review Issues\n\n{issue_descriptions}\n\n## Files\n{files}"
     d. Resolve "coder" role adapter
     e. ensure_agent_ready(coder)
     f. Execute fix:
        await coder.run_task(
            workspace=task_run.workspace_path,
            instruction=fix_instruction,
            log_fn=_review_log,
        )
     g. Log: "Fix attempt complete, re-running review"
     h. CONTINUE loop (re-review)

After loop exhaustion:
  Log: "Review issues remain after {max_retries} retries, proceeding to approval"
  (Phase completes successfully — human will review the PR)
```

### Key Behaviors

- **Review temperature:** 0.2 (lower than planning's 0.3, for stricter output)
- **Critical issues always block approval** regardless of LLM "approved" flag
- **Auto-fix uses the "coder" role,** not the "reviewer" role
- **Exhausted retries do NOT fail the phase** — the pipeline proceeds to PR creation
- **Total possible review iterations:** `max_retries + 1` (1 initial + N retries)

---

## Phase 6: Approval

**File:** `backend/worker/phases/approval.py`
**Purpose:** Push branch to remote and create Pull Request

### Flow

```
1. Connect via SSH to workspace server
2. Construct repo base URL:
   GitHub: https://github.com/{owner}/{repo}.git
   Gitea:  {settings.gitea_url}/{owner}/{repo}.git
3. Get authenticated URL (SSH-first, HTTPS fallback)
4. Set remote URL:
   Command: git remote set-url origin {auth_url}
5. Push branch:
   Command: git push -u origin {branch_name}
6. Create PR via GitProvider API:
   title = "[AI] {task_run.title}"
   body = PR body with review summary
   head = task_run.branch_name
   base = task_run.default_branch
7. Store PR URL:
   task_run.pr_url = pr_url
8. Broadcast event: "approval_requested"
```

### PR Body Template

```markdown
## AI-Generated Pull Request

### Task
{task_run.title}

### Description
{task_run.description}

### Review Summary
- **Automated Review**: Passed|Needs attention
- **Issues Found**: {N}
- **Suggestions**: {N}

### Suggestions from AI Reviewer
- suggestion 1
- suggestion 2
- ...

---
*This PR was created automatically by the AI Development Infrastructure.*
*Please review carefully before merging.*
```

### Approval Parking

The pipeline sequencer handles parking AFTER this phase completes:
```
If phase_exec.trigger_mode == "wait_for_approval":
  → Set phase status to "waiting"
  → Set run.status = "awaiting_approval"
  → Set run.approval_requested_at = now
  → Pipeline RETURNS (pauses)
```

The engine resumes when `run.approved` is set externally (via API).

---

## Phase 7: Finalization

**File:** `backend/worker/phases/finalization.py`
**Purpose:** Post-pipeline cleanup and PR comment posting

### Flow

```
1. fix-pr workflow (push to existing PR):
   If pr_branch exists AND no pr_url:
     a. Connect SSH, get auth URL
     b. Command: git remote set-url origin {auth_url}
     c. Command: git push origin {pr_branch}

2. Post review comment on source PR:
   If review_result exists AND pr_number exists:
     Call: provider.post_pr_comment(repo_path, pr_number, body)
     On failure: log warning (non-fatal)

3. Log PR URL (if available)

4. Cleanup:
   Connect SSH → RemoteSandbox.stop_sandbox(workspace_path)
   Stops any Docker sandbox containers started during workspace_setup
```

### Review Comment Format

```markdown
## AI Code Review

**Status**: Approved|Changes Requested
**Issues Found**: {N}
**Suggestions**: {N}

### Issues

- **[critical]** `file.py:42` Description of issue
- **[major]** `utils.py` Another issue

### Suggestions

- Suggestion text here
- Another suggestion

---
*Generated by AI Development Infrastructure*
```

---

## Optional: PR Fetch Phase

**File:** `backend/worker/phases/pr_fetch.py`
**Purpose:** Fetch PR diff and comments via git provider API (no SSH needed)
**Used in:** pr-review workflow

### Flow

```
1. Extract pr_number from:
   - task_source_meta.pr_number (direct)
   - task_source_meta.pr_url (parsed via regex)
2. Resolve repo_path: "{owner}/{repo}"
3. Fetch diff:
   diff = await provider.get_pr_diff(repo_path, pr_number)
4. Fetch comments:
   comments = await provider.get_pr_comments(repo_path, pr_number)
5. Store results:
   task_run.coding_results = {
       "pr_diff": diff[:50000],      # Max 50,000 chars
       "pr_comments": comments[:50], # Max 50 comments
       "pr_number": pr_number,
       "repo_path": repo_path,
   }
```

### PR URL Parsing

```python
Pattern: r"https?://[^/]+/([^/]+/[^/]+)/pulls?/(\d+)"
Matches:
  - https://github.com/owner/repo/pull/123
  - https://gitea.example.com/owner/repo/pulls/456
```

---

## Optional: Task Creation Phase

**File:** `backend/worker/phases/task_creation.py`
**Purpose:** Create child TaskRuns from planning subtasks (decomposition workflow)

### Flow

```
1. Get subtasks from task_run.planning_result.subtasks
   If empty → return {"children_created": 0}

2. Look up "small-task" workflow template:
   template = await WorkflowTemplateRepository.get_by_name("small-task")

3. Check auto_execute setting:
   project.ai_config["auto_execute_subtasks"] (default: True)
   child_status = "pending" if auto_execute else "awaiting_approval"

4. For each subtask:
   Create child TaskRun:
     task_id = "{parent.task_id}-sub-{i+1}"
     project_id = parent.project_id
     title = subtask.title
     description = subtask.description
     branch_name = parent.branch_name (shared)
     workspace_path = parent.workspace_path (shared)
     parent_run_id = parent.id
     workflow_template_id = small-task template ID
     status = child_status
     planning_result = {"subtasks": [synthesized_subtask]}

5. Return: {"children_created": N, "child_run_ids": [...]}
```

### Key Behaviors

- Child tasks **share** the parent's branch and workspace
- Each child gets a **pre-populated planning_result** so it skips the planning phase
- `auto_execute_subtasks` setting controls whether children start automatically or wait for approval

---

## CLI Adapter

**File:** `backend/services/adapters/cli_adapter.py`

### Supported Agents

| Agent | Generate Command | Task Command | Check Command |
|-------|-----------------|-------------|---------------|
| `claude` | `cat {file} \| claude --print` | `cd {ws} && cat {file} \| claude --dangerously-skip-permissions --print` | `command -v claude` |
| `codex` | `codex --quiet -p {file}` | `cd {ws} && codex -p {file}` | `command -v codex` |
| `aider` | `aider --yes --no-git --message-file {file}` | `cd {ws} && aider --yes --message-file {file}` | `command -v aider` |
| `opencode` | `cat {file} \| opencode` | `cd {ws} && opencode -p {file}` | `command -v opencode` |
| `gemini` | `cat {file} \| gemini` | `cd {ws} && gemini -p {file}` | `command -v gemini` |
| `kimi` | `cat {file} \| kimi` | `cd {ws} && kimi -p {file}` | `command -v kimi` |

### Non-Root Requirement

Only `claude` is in `_NEEDS_NON_ROOT` set. Claude CLI blocks `--dangerously-skip-permissions` when running as root, so the adapter wraps commands to run as a non-root user.

### generate() Method

```
1. Prepend system_prompt to prompt (if provided)
2. Write prompt to temp file on remote:
   Command: TMPF=$(mktemp) && echo '{escaped}' > "$TMPF" && echo "$TMPF"
   Timeout: 10 seconds
3. Run agent generate command:
   Timeout: 300 seconds (5 minutes)
4. Cleanup temp file:
   Command: rm -f {prompt_file}
   Timeout: 5 seconds
5. Return stdout as response text
```

### run_task() Method

```
1. Check agent availability:
   If not available → return {exit_code: 127}

2. Write instruction to temp file:
   Timeout: 10 seconds

3. Build command from AGENT_COMMANDS[agent]["task"]

4. If agent needs non-root AND SSH user is root:
   a. If worker_user set (pre-configured):
      Wrap with _wrap_for_user()
   b. Else:
      Wrap with _wrap_non_root()

5. Execute command:
   Timeout: 600 seconds (10 minutes)

6. Cleanup temp file:
   Timeout: 5 seconds

7. Detect changed files:
   Command: cd {workspace} && (
     git diff --name-only HEAD 2>/dev/null;
     git diff --cached --name-only 2>/dev/null;
     git ls-files --others --exclude-standard 2>/dev/null;
     git diff --name-only $(git merge-base HEAD main 2>/dev/null ||
       git merge-base HEAD origin/main 2>/dev/null || echo HEAD~1)..HEAD 2>/dev/null
   ) | sort -u
   Timeout: 10 seconds

8. Return:
   {output, stderr, exit_code, elapsed_s, files_changed, command}
```

### _wrap_non_root() — Inline User Creation

```bash
# Create user idempotently
id -u coder &>/dev/null || useradd -m -s /bin/bash coder

# Copy CLI binaries (not symlink — /root is 700)
mkdir -p /home/coder/.local/bin
for b in /root/.local/bin/* /root/.claude/bin/*; do
  [ -f "$b" ] && cp -f "$b" /home/coder/.local/bin/ 2>/dev/null
done

# Copy Claude config + API keys
rm -rf /home/coder/.claude 2>/dev/null
cp -a /root/.claude /home/coder/.claude 2>/dev/null || true
chown -R coder:coder /home/coder

# Set workspace ownership
chown -R coder:coder {workspace}
chown coder:coder {instruction_file}

# Git safe directory
runuser -u coder -- git config --global --add safe.directory {workspace}

# Run command as coder with explicit PATH
runuser -u coder -- bash -c 'export PATH="/home/coder/.local/bin:/home/coder/.claude/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" && {cmd}'
```

### _wrap_for_user() — Pre-configured User

```bash
# Set workspace ownership (no user creation or binary copy)
chown -R {username}:{username} {workspace}
chown {username}:{username} {instruction_file}

# Git safe directory
runuser -u {username} -- git config --global --add safe.directory {workspace}

# Run command as user with explicit PATH
runuser -u {username} -- bash -c 'export PATH="/home/{username}/.local/bin:/home/{username}/.claude/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" && {cmd}'
```

---

## Broadcaster

**File:** `backend/worker/broadcaster.py`

### Singleton

```python
broadcaster = Broadcaster()  # Global singleton used by all phases
```

### Subscription Model

```
Run-specific subscribers: dict[int, list[asyncio.Queue]]
  → Per-run WebSocket clients
Global subscribers: list[asyncio.Queue]
  → All WebSocket clients (for events)
```

### log() Method

```python
async def log(run_id, message, level="info", phase=None, metadata=None):
```

1. **Persist to DB:** Creates `TaskLog` entry via separate DB session
2. **Broadcast to subscribers:** Pushes payload to all queues for that run_id
3. **Payload format:**
   ```json
   {
     "type": "log",
     "run_id": 42,
     "timestamp": "2026-02-21T...",
     "level": "info",
     "phase": "coding",
     "message": "Subtask 1/3: Implement auth",
     "metadata_": { ... }
   }
   ```

### event() Method

```python
async def event(run_id, event_type, data=None):
```

Broadcasts to **global** subscribers only. Event types:
- `run_started`, `run_completed`, `run_failed`, `run_timeout`, `run_rejected`
- `phase_changed`, `phase_completed`, `phase_failed`, `phase_waiting`
- `approval_requested`

### Metadata Truncation

```python
make_log_metadata(category, **kwargs):

Categories: "system_prompt", "prompt", "response", "ssh_command"

Truncation limits:
  - prompt_text, system_prompt_text: 10,000 chars max
  - All other string fields: 2,000 chars max

If truncated, adds:
  - {key}_truncated: True
  - {key}_original_length: N
```

---

## Helper Functions

**File:** `backend/worker/phases/_helpers.py`

### Default Phase Roles

```python
_DEFAULT_PHASE_ROLES = {
    "planning":  "planner",
    "coding":    "coder",
    "reviewing": "reviewer",
}
```

`get_phase_role(phase_name, phase_config)`:
1. Check `phase_config.get("role")` first
2. Fall back to `_DEFAULT_PHASE_ROLES`
3. Final fallback: use phase_name itself

### ensure_agent_ready()

```
Called before coding and reviewing phases.
Does nothing for non-CLI adapters (Ollama, OpenHands).

Step 1: Check if agent binary exists as SSH user (root)
  Command: command -v {agent}
  Timeout: 10 seconds

Step 2: Auto-install if missing
  Call: AgentInstallService(ssh).install_agent(agent)
  On failure: raise RuntimeError

Step 3: Non-root setup (only for agents in _NEEDS_NON_ROOT = {"claude"})
  Only applies when SSH user is root.

  a. If adapter.worker_user is set (pre-configured):
     Call: WorkerUserService.sync_agents(username)
  b. Else:
     Call: WorkerUserService.setup(username="coder")
     If user creation fails: raise RuntimeError

Step 4: Direct binary copy fallback
  If agent not found in worker user's PATH:
    a. Find binary as root: command -v {agent}
       Timeout: 10 seconds
    b. If not found as root: reinstall via AgentInstallService
    c. Resolve real binary path: readlink -f {agent_path}
       Timeout: 10 seconds
    d. Copy binary:
       mkdir -p /home/{user}/.local/bin &&
       cp -f {real_path} /home/{user}/.local/bin/{agent} &&
       chmod +x /home/{user}/.local/bin/{agent} &&
       chown {user}:{user} /home/{user}/.local/bin/{agent}
       Timeout: 120 seconds (binary is ~225MB)
    e. Re-check: WorkerUserService.check_status(username)

Step 5: Verify
  If agent in worker user's agents:
    Set adapter.worker_user = username
  Else:
    raise RuntimeError (agent still not available)
```

### SSH Connection Helpers

```python
get_workspace_server(task_run, session) -> WorkspaceServer
  # Loads via ProjectConfig → WorkspaceServer relationship
  # Raises ValueError if not configured

get_ssh_for_run(task_run, session) -> SSHService
  # Creates SSHService.for_server(workspace_server)

get_workspace_server_id(task_run, session) -> int | None
  # Lightweight: just returns the ID, not full model
```

---

## Timeout & Limit Reference

### SSH Command Timeouts

| Operation | Timeout | Location |
|-----------|---------|----------|
| Agent check (`command -v`) | 10s | `_helpers.py`, `cli_adapter.py` |
| Write prompt/instruction to temp file | 10s | `cli_adapter.py` |
| Cleanup temp file (`rm -f`) | 5s | `cli_adapter.py` |
| Agent `generate()` (LLM response) | 300s (5min) | `cli_adapter.py` |
| Agent `run_task()` (coding execution) | 600s (10min) | `cli_adapter.py` |
| Git diff detection | 10s | `cli_adapter.py` |
| Test execution (`make test`) | 300s (5min) | `testing.py` |
| Scaffold template script | 300s (5min) | `workspace_setup.py` |
| Binary copy (225MB agent) | 120s (2min) | `_helpers.py` |
| `readlink -f` (resolve symlinks) | 10s | `_helpers.py` |

### API Service Timeouts

| Service | Timeout | Location |
|---------|---------|----------|
| Ollama `/api/generate` | 180s (3min) | `ollama_service.py` |
| Ollama `/api/chat` | 180s (3min) | `ollama_service.py` |
| OpenHands `/api/agent/run` | 600s (10min) | `openhands_service.py` |

### Data Truncation Limits

| Data | Limit | Location |
|------|-------|----------|
| Log metadata: prompt/system_prompt | 10,000 chars | `broadcaster.py` |
| Log metadata: other fields | 2,000 chars | `broadcaster.py` |
| Review diff sent to LLM | 10,000 chars | `reviewing.py` |
| PR diff from API | 50,000 chars | `pr_fetch.py` |
| PR comments from API | 50 comments | `pr_fetch.py` |
| Test stdout in results | 2,000 chars | `testing.py` |
| Test stderr in results | 1,000 chars | `testing.py` |
| Context doc preview | 100 chars/doc | `planning.py` |
| SSH log stdout/stderr preview | 500 chars | `cli_adapter.py` |

### Retry & Concurrency Limits

| Parameter | Default | Location |
|-----------|---------|----------|
| Max concurrent runs | 3 | `config.py` |
| Poll interval | 2s | `config.py` |
| Approval timeout | 24h | `config.py` |
| Phase max retries | 3 | `PhaseExecution.max_retries` |
| Review max retries | `task_run.max_retries` (3) | `reviewing.py` |
| Agent max_iterations | 20 | `coding.py` |
| Files hint display | 5 files max | `coding.py` |
| Files changed display | 5 files max | `coding.py` |
| SSH command preview | 300 chars | `cli_adapter.py` |

### LLM Parameters

| Phase | Temperature | Max Tokens (num_predict) |
|-------|------------|--------------------------|
| Planning | 0.3 | 2048 |
| Coding | N/A (CLI agent) | N/A |
| Reviewing | 0.2 | 2048 |

---

## Workflow Templates

### Template Resolution

```python
_resolve_workflow_phases(run, session):
  1. Explicit: run.workflow_template_id → WorkflowTemplate lookup
  2. Labels: run.task_source_meta.labels → match_labels()
  3. Default: WorkflowTemplateRepository.get_default()
  4. Fallback: hardcoded PHASE_NAMES
```

### Template Phase Config

Each phase in a workflow template can specify:

```python
{
    "phase_name": "coding",
    "enabled": True,              # Include/exclude phase
    "trigger_mode": "auto",       # "auto" | "wait_for_approval" | "wait_for_trigger"
    "role": "coder",              # Override default role
    "max_retries": 3,             # Override retry count
    "agent_override": "claude",   # Override agent selection
    "notify_source": False,       # Notify task source on completion
    "phase_config": {             # Arbitrary config passed to phase
        "role": "senior-coder",
        "custom_key": "value"
    }
}
```

### Standard Workflow Names

| Workflow | Phases | Purpose |
|----------|--------|---------|
| `default` | All 8 phases | Full pipeline |
| `small-task` | workspace_setup → init → coding → approval | Quick tasks without planning/review |
| `pr-review` | pr_fetch → reviewing → finalization | Review existing PR |
| `fix-pr` | workspace_setup → init → coding → reviewing → approval → finalization | Fix issues from PR review |
| `planner` | workspace_setup → init → planning → task_creation | Decompose and create subtasks |

---

## Data Flow Diagram

```
                          ┌──────────────┐
                          │   TaskRun    │
                          │  status=     │
                          │  "pending"   │
                          └──────┬───────┘
                                 │
                    WorkerEngine._dispatch_pending()
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   execute_pipeline()    │
                    │  status → "running"     │
                    └────────────┬───────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
  ┌──────────────┐      ┌──────────────┐       ┌──────────────┐
  │ Phase 0:     │      │ Phase 1:     │       │ Phase 2:     │
  │ workspace    │─────▶│ init         │──────▶│ planning     │
  │ setup        │      │              │       │              │
  │              │      │ Creates      │       │ Decomposes   │
  │ Clones repo  │      │ branch,      │       │ task into    │
  │ via SSH      │      │ gets context │       │ subtasks     │
  └──────────────┘      └──────────────┘       └──────┬───────┘
                                                      │
                                    planning_result.subtasks
                                                      │
         ┌────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────┐      ┌──────────────┐       ┌──────────────┐
  │ Phase 3:     │      │ Phase 4:     │       │ Phase 5:     │
  │ coding       │─────▶│ testing      │──────▶│ reviewing    │
  │              │      │              │       │              │
  │ Executes     │      │ make test    │       │ AI review    │
  │ subtasks     │      │ (best-effort)│       │ + auto-fix   │
  │ via agent    │      │              │       │ retry loop   │
  └──────────────┘      └──────────────┘       └──────┬───────┘
                                                      │
                                            review_result.approved
                                                      │
         ┌────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────┐                            ┌──────────────┐
  │ Phase 6:     │                            │ Phase 7:     │
  │ approval     │───────────────────────────▶│ finalization │
  │              │  (may pause here for       │              │
  │ Push branch, │   human approval)          │ Cleanup,     │
  │ create PR    │                            │ post comment │
  └──────────────┘                            └──────┬───────┘
                                                     │
                                                     ▼
                                          ┌──────────────────┐
                                          │    TaskRun       │
                                          │  status=         │
                                          │  "completed"     │
                                          └──────────────────┘
```

### Phase Data Dependencies

```
workspace_setup → workspace_result.workspace_path
                     ↓
init            → planning_result.context_docs  (context for planner)
                → branch_name (may update for fix-pr)
                     ↓
planning        → planning_result.subtasks      (work items for coder)
                     ↓
coding          → coding_results.results        (files changed per subtask)
                     ↓
testing         → test_results                  (pass/fail, informational)
                     ↓
reviewing       → review_result.approved        (gate for PR creation)
                → review_result.issues
                → review_result.suggestions
                     ↓
approval        → pr_url                        (created PR link)
                     ↓
finalization    → cleanup                       (sandbox stop, PR comment)
```

---

## TaskRun Status State Machine

```
                    ┌──────────┐
                    │ pending  │◀────── Created / Resumed after approval
                    └────┬─────┘
                         │ dispatch
                         ▼
                    ┌──────────┐
              ┌────▶│ running  │◀────── Pipeline executing phases
              │     └────┬─────┘
              │          │
              │    ┌─────┼────────────────┐
              │    │     │                │
              │    │     ▼                ▼
              │    │ ┌──────────────┐ ┌──────────────────┐
              │    │ │ awaiting_    │ │ waiting_for_     │
              │    │ │ approval     │ │ trigger          │
              │    │ └──────┬───┬──┘ └────────┬──────────┘
              │    │        │   │             │
              │    │  approved  rejected   triggered
              │    │        │   │             │
              │    │        ▼   │             │
              │    │ ┌──────┐   │    ┌────────┘
              │    │ │pending│   │    │
              │    │ └──┬───┘   │    │
              │    │    │       │    │
              │    └────┘       │    │
              │                 │    │
              └─────────────────┘────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          ▼
         ┌─────────┐ ┌──────┐ ┌─────────┐
         │completed│ │failed│ │ timeout  │
         └─────────┘ └──────┘ └─────────┘

         Also: "cancelled" (external cancellation checked at phase start)
```
