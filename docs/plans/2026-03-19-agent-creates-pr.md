# Agent Creates PR Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an `agent_creates_pr` flag to `AgentSettings` so agents that support it can commit, push, and create the PR themselves — the approval phase then skips the git work and goes straight to waiting for human review.

**Architecture:** New boolean column on `AgentSettings` (default `False`). When `True`, the coding phase appends a git/PR instruction block to the consolidated prompt and captures the PR URL from the agent's JSON output. The approval phase detects `task_run.pr_url` is already populated and skips push + PR creation.

**Tech Stack:** Python/SQLAlchemy/Alembic (backend), React/TypeScript (frontend), pytest (tests)

---

### Task 1: Alembic migration

**Files:**
- Create: `alembic/versions/022_agent_creates_pr.py`

**Step 1: Write the migration file**

```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add agent_creates_pr to agent_settings.

Revision ID: 022
Revises: 021
"""

import sqlalchemy as sa

from alembic import op

revision = "022"
down_revision = "021"


def upgrade() -> None:
    op.add_column(
        "agent_settings",
        sa.Column("agent_creates_pr", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("agent_settings", "agent_creates_pr")
```

**Step 2: Apply and verify**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```
Expected: `Running upgrade 021 -> 022`

**Step 3: Commit**

```bash
git add alembic/versions/022_agent_creates_pr.py
git commit -m "feat: add agent_creates_pr migration"
```

---

### Task 2: Model + schema

**Files:**
- Modify: `backend/models/agents.py` (after `consolidated_default` column, ~line 107)
- Modify: `backend/schemas/agents.py` (both `AgentSettingsIn` and `AgentSettingsOut`)
- Modify: `frontend/src/types/agents.ts`

**Step 1: Add column to model**

In `backend/models/agents.py`, after the `consolidated_default` column add:

```python
    agent_creates_pr = Column(
        Boolean, nullable=False, default=False
    )
```

**Step 2: Add to Pydantic schemas**

In `backend/schemas/agents.py`:

`AgentSettingsIn` — add after `consolidated_default`:
```python
    agent_creates_pr: bool | None = None
```

`AgentSettingsOut` — add after `consolidated_default: bool = True`:
```python
    agent_creates_pr: bool = False
```

**Step 3: Add to frontend type**

In `frontend/src/types/agents.ts`, after `consolidated_default: boolean;`:
```typescript
  agent_creates_pr: boolean;
```

**Step 4: Run lint/typecheck on changed files**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/models/agents.py backend/schemas/agents.py --fix
docker compose -f docker-compose.dev.yml exec backend pyright backend/models/agents.py backend/schemas/agents.py
```
Expected: no errors

**Step 5: Commit**

```bash
git add backend/models/agents.py backend/schemas/agents.py frontend/src/types/agents.ts
git commit -m "feat: add agent_creates_pr column and schema field"
```

---

### Task 3: Prompt injection constant

**Files:**
- Modify: `backend/worker/phases/_coding_utils.py`

**Step 1: Write a failing test**

Add to `tests/unit/test_coding.py`:

```python
def test_agent_creates_pr_instruction_block():
    from backend.worker.phases._coding_utils import build_agent_creates_pr_instructions
    result = build_agent_creates_pr_instructions(
        branch_name="feat/my-task", task_title="Fix the bug", base_branch="main"
    )
    assert "git push" in result
    assert "feat/my-task" in result
    assert "Fix the bug" in result
    assert "pr_url" in result
```

**Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_coding.py::TestCoding::test_agent_creates_pr_instruction_block -v 2>/dev/null || docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_coding.py -k "test_agent_creates_pr_instruction_block" -v
```
Expected: FAIL with `ImportError` or `AttributeError`

**Step 3: Add the constant and function to `_coding_utils.py`**

After the `CONSOLIDATED_TEMPLATE` constant (around line 130), add:

```python
_AGENT_CREATES_PR_INSTRUCTIONS = """
## Git & PR
After all code changes and commits are complete:
1. Push the branch to origin: `git push -u origin {branch_name}`
2. Create a PR using the gh CLI:
   ```
   gh pr create --title {pr_title_quoted} --body "Automated PR for: {task_title}" --base {base_branch}
   ```
   If gh is unavailable, use the git provider's API or CLI equivalent.
3. Add the PR URL to your JSON output as `"pr_url"`.

Your JSON summary must include the `pr_url` field:
```json
{{{{
  "plan": {{{{...}}}},
  "review": {{{{...}}}},
  "pr_url": "https://..."
}}}}
```
"""


def build_agent_creates_pr_instructions(
    branch_name: str, task_title: str, base_branch: str
) -> str:
    """Return the git/PR instruction block to append to the consolidated prompt."""
    import shlex

    pr_title_quoted = shlex.quote(f"[AI] {task_title}")
    return _AGENT_CREATES_PR_INSTRUCTIONS.format(
        branch_name=branch_name,
        pr_title_quoted=pr_title_quoted,
        task_title=task_title,
        base_branch=base_branch,
    )
```

**Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_coding.py -k "test_agent_creates_pr_instruction_block" -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/worker/phases/_coding_utils.py tests/unit/test_coding.py
git commit -m "feat: add build_agent_creates_pr_instructions helper"
```

---

### Task 4: Coding phase — inject instructions + capture pr_url

**Files:**
- Modify: `backend/worker/phases/_coding_consolidated.py`
- Modify: `backend/worker/phases/coding.py`
- Modify: `tests/unit/test_coding.py`

The coding phase calls `run_consolidated()`. We need to:
1. Pass `agent_creates_pr: bool` into `run_consolidated`
2. Append the instruction block to the prompt when True
3. After parsing the JSON summary, capture `pr_url` and store it on `task_run`

**Step 1: Write failing test for pr_url capture**

Add to `tests/unit/test_coding.py`:

```python
async def test_consolidated_captures_pr_url(self, db_session, make_task_run, mock_services):
    """When agent outputs pr_url in JSON, it gets stored on task_run."""
    from backend.worker.phases._coding_consolidated import _parse_consolidated_summary

    agent_output = """
Some output here.
```json
{
  "plan": {"subtasks": [{"title": "t", "description": "d", "files_affected": []}], "complexity": "simple"},
  "review": {"approved": true, "issues": [], "suggestions": []},
  "pr_url": "https://github.com/org/repo/pull/42"
}
```
"""
    summary = _parse_consolidated_summary(agent_output)
    assert summary.get("pr_url") == "https://github.com/org/repo/pull/42"
```

**Step 2: Run to verify it passes (or fails)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_coding.py -k "test_consolidated_captures_pr_url" -v
```
Note: `_parse_consolidated_summary` already extracts all JSON keys, so this test may already pass. If so, skip to step 3.

**Step 3: Update `run_consolidated` signature in `_coding_consolidated.py`**

Add `agent_creates_pr: bool = False` parameter to `run_consolidated`:

```python
async def run_consolidated(
    task_run: TaskRun,
    session: AsyncSession,
    adapter: object,
    agent_mode: str,
    system_prompt: str,
    settings_kwargs: dict,
    extra_params: dict,
    use_sessions: bool,
    session_id: str | None,
    session_is_new: bool,
    phase_exec_row: PhaseExecution | None,
    ws_id: int | None,
    agent_creates_pr: bool = False,   # ← ADD THIS
) -> None:
```

**Step 4: Import and inject the instruction block**

In `_coding_consolidated.py`, add import at top:
```python
from backend.worker.phases._coding_utils import (
    CONSOLIDATED_TEMPLATE,
    build_agent_creates_pr_instructions,  # ← ADD
    ...
)
```

After `consolidated_prompt = CONSOLIDATED_TEMPLATE.format(...)` (around line 65), add:

```python
    if agent_creates_pr:
        consolidated_prompt += "\n" + build_agent_creates_pr_instructions(
            branch_name=task_run.branch_name,
            task_title=task_run.title or "Task",
            base_branch=str(task_run.default_branch),
        )
```

**Step 5: Capture pr_url after summary parsing**

In `_coding_consolidated.py`, after these lines (around line 200):
```python
    summary = _parse_consolidated_summary(agent_output)
    plan_data = summary.get("plan", {})
    review_data = summary.get("review", {})
```

Add:
```python
    # Capture PR URL if agent created the PR
    agent_pr_url = summary.get("pr_url")
    if agent_pr_url and isinstance(agent_pr_url, str) and agent_pr_url.startswith("http"):
        task_run.pr_url = agent_pr_url
        await broadcaster.log(
            task_run.id, f"Agent created PR: {agent_pr_url}", phase="coding"
        )
```

**Step 6: Pass flag from `coding.py`**

In `backend/worker/phases/coding.py`, find the `run_consolidated(...)` call (around line 219). Add the new kwarg:

```python
        await run_consolidated(
            task_run,
            session,
            adapter,
            agent_mode,
            system_prompt,
            settings_kwargs,
            extra_params,
            use_sessions,
            session_id,
            session_is_new,
            phase_exec_row,
            ws_id,
            agent_creates_pr=bool(
                resolved.agent_settings and resolved.agent_settings.agent_creates_pr
            ),
        )
```

**Step 7: Write integration test**

Add to `tests/unit/test_coding.py` in `TestCoding`:

```python
async def test_agent_creates_pr_appends_instructions(self, db_session, make_task_run, mock_services):
    """When agent_creates_pr=True, prompt includes git/PR instructions."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from backend.worker.phases._coding_consolidated import run_consolidated
    from backend.models import AgentSettings, PhaseExecution

    run = make_task_run()
    run.branch_name = "feat/test-branch"
    run.default_branch = "main"
    db_session.add(run)
    await db_session.commit()

    captured_prompts = []

    mock_adapter = MagicMock()
    mock_adapter.provider_name = "claude"
    mock_adapter.generate = AsyncMock(return_value='{"plan":{"subtasks":[],"complexity":"simple"},"review":{"approved":true,"issues":[],"suggestions":[]},"pr_url":"https://github.com/o/r/pull/1"}')

    async def capture_generate(prompt, **kwargs):
        captured_prompts.append(prompt)
        return '{"plan":{"subtasks":[],"complexity":"simple"},"review":{"approved":true,"issues":[],"suggestions":[]},"pr_url":"https://github.com/o/r/pull/1"}'

    mock_adapter.generate = capture_generate

    with patch("backend.worker.phases._coding_consolidated.broadcaster", MagicMock(log=AsyncMock(), event=AsyncMock())):
        with patch("backend.worker.phases._coding_consolidated.record_invocation_cost", AsyncMock()):
            await run_consolidated(
                run, db_session, mock_adapter, "generate", "", {}, {},
                False, None, False, None, None,
                agent_creates_pr=True,
            )

    assert captured_prompts, "adapter.generate was never called"
    assert "git push" in captured_prompts[0]
    assert "feat/test-branch" in captured_prompts[0]
    await db_session.refresh(run)
    assert run.pr_url == "https://github.com/o/r/pull/1"
```

**Step 8: Run all coding tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_coding.py -v
```
Expected: all pass

**Step 9: Lint/typecheck**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/worker/phases/_coding_consolidated.py backend/worker/phases/coding.py --fix
docker compose -f docker-compose.dev.yml exec backend pyright backend/worker/phases/_coding_consolidated.py backend/worker/phases/coding.py
```

**Step 10: Commit**

```bash
git add backend/worker/phases/_coding_consolidated.py backend/worker/phases/coding.py tests/unit/test_coding.py
git commit -m "feat: inject PR instructions and capture pr_url in consolidated coding"
```

---

### Task 5: Approval phase — skip git work if pr_url already set

**Files:**
- Modify: `backend/worker/phases/approval.py`
- Modify: `tests/unit/test_approval.py`

**Step 1: Write failing test**

Add to `tests/unit/test_approval.py` in `TestApproval`:

```python
async def test_skips_push_and_pr_when_pr_url_already_set(
    self, db_session, make_task_run, mock_services
):
    """When task_run.pr_url is already set (agent created it), approval skips git work."""
    run = make_task_run(review_result={"approved": True, "issues": [], "suggestions": []})
    run.pr_url = "https://github.com/org/repo/pull/99"
    db_session.add(run)
    await db_session.commit()

    patches = _approval_patches()
    with (
        patches["get_git_provider"] as mock_factory,
        patches["get_auth_url"] as mock_auth,
        patches["get_ssh_for_run"],
        patches["RemoteGitOps"] as mock_remote_git_cls,
        patches["broadcaster"],
    ):
        mock_remote_git = mock_remote_git_cls.return_value
        mock_remote_git.run_git = AsyncMock(return_value=_git_result("abc1234 some commit\n"))

        await approval.run(run, db_session, mock_services)

    # Git provider create_pr should NOT be called
    mock_factory.return_value.create_pr.assert_not_called()
    # Auth URL and push should NOT be called
    mock_auth.assert_not_called()
    # pr_url must still be the original value
    await db_session.refresh(run)
    assert run.pr_url == "https://github.com/org/repo/pull/99"
```

**Step 2: Run to verify it fails**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_approval.py -k "test_skips_push_and_pr_when_pr_url_already_set" -v
```
Expected: FAIL (approval phase currently always pushes)

**Step 3: Modify `approval.py`**

In `backend/worker/phases/approval.py`, the `run()` function currently always pushes and creates PR. Wrap the git work in an `if not task_run.pr_url:` block.

Find the section starting with `# Ensure remote has auth credentials, then push` (around line 74) through `await broadcaster.event(task_run.id, "approval_requested", {"pr_url": pr_url})` (around line 120).

Replace the entire push+PR section with:

```python
    if task_run.pr_url:
        # Agent already pushed and created the PR during coding phase
        await broadcaster.log(
            task_run.id,
            f"PR already created by agent: {task_run.pr_url}",
            phase="approval",
        )
    else:
        # Standard flow: push branch then create PR via API / gh CLI
        project_token = await get_project_token(task_run, session)

        base_url = get_repo_https_url(task_run.git_provider, task_run.repo_owner, task_run.repo_name)
        auth_url, method = await get_auth_url(
            base_url, task_run.git_provider, ssh, token_override=project_token
        )
        await broadcaster.log(
            task_run.id,
            f"Pushing branch {task_run.branch_name} (auth={method})",
            phase="approval",
        )
        await remote_git.run_git(["remote", "set-url", "origin", auth_url], cwd=cwd)
        await remote_git.run_git(["push", "-u", "origin", task_run.branch_name], cwd=cwd)
        await broadcaster.log(task_run.id, "Branch pushed successfully", phase="approval")

        pr_body = _build_pr_body(task_run, review)
        repo_path = f"{task_run.repo_owner}/{task_run.repo_name}"
        pr_title = f"[AI] {task_run.title}"

        await broadcaster.log(
            task_run.id,
            f"Creating PR: {pr_title} on {task_run.git_provider}",
            phase="approval",
        )

        pr_url: str | None = None
        if task_run.git_provider == "github":
            pr_url = await _try_gh_pr_create(ssh, cwd, pr_title, pr_body, task_run)

        if not pr_url:
            provider = get_git_provider(
                task_run.git_provider, get_http_client(), access_token=project_token
            )
            pr_url = await provider.create_pr(
                repo_path,
                title=pr_title,
                body=pr_body,
                head=task_run.branch_name,
                base=task_run.default_branch,
            )

        await broadcaster.log(task_run.id, f"PR created: {pr_url}", phase="approval")
        task_run.pr_url = pr_url
        await session.commit()

    await broadcaster.event(task_run.id, "approval_requested", {"pr_url": task_run.pr_url})
```

Note: the `project_token` variable was previously fetched unconditionally at line ~73. Move it inside the `else` block since it's only needed for the push path.

**Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_approval.py -k "test_skips_push_and_pr_when_pr_url_already_set" -v
```
Expected: PASS

**Step 5: Run full approval test suite**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_approval.py -v
```
Expected: all pass

**Step 6: Lint/typecheck**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/worker/phases/approval.py --fix
docker compose -f docker-compose.dev.yml exec backend pyright backend/worker/phases/approval.py
```

**Step 7: Commit**

```bash
git add backend/worker/phases/approval.py tests/unit/test_approval.py
git commit -m "feat: approval phase skips push+PR when agent already created it"
```

---

### Task 6: Frontend — add toggle to AgentSettings UI

**Files:**
- Modify: `frontend/src/pages/AgentSettings.tsx`
- Modify: `frontend/src/__tests__/AgentSettings.test.tsx`

**Step 1: Add state and save logic to `AgentSettings.tsx`**

Find where `consolidatedDefault` state is declared (around line 81):
```tsx
const [consolidatedDefault, setConsolidatedDefault] = useState(agent.consolidated_default ?? true);
```

After it, add:
```tsx
const [agentCreatesPr, setAgentCreatesPr] = useState(agent.agent_creates_pr ?? false);
```

Find the `useEffect` that resets state on agent change (around line 100):
```tsx
setConsolidatedDefault(agent.consolidated_default ?? true);
```
After it add:
```tsx
setAgentCreatesPr(agent.agent_creates_pr ?? false);
```

Find the save payload (around line 152):
```tsx
consolidated_default: consolidatedDefault,
```
After it add:
```tsx
agent_creates_pr: agentCreatesPr,
```

**Step 2: Add toggle in the UI**

Find the Consolidated Mode toggle block (around line 387):
```tsx
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs text-gray-500">Consolidated Mode</label>
                  ...
                </div>
                <Toggle checked={consolidatedDefault} ... />
              </div>
```

After this block, add:
```tsx
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs text-gray-500">Agent Creates PR</label>
                  <p className="text-xs text-gray-600 mt-0.5">
                    Agent commits, pushes, and creates PR itself
                  </p>
                </div>
                <Toggle
                  checked={agentCreatesPr}
                  onChange={setAgentCreatesPr}
                  ariaLabel="Toggle agent creates PR"
                />
              </div>
```

**Step 3: Run frontend lint**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx eslint src/pages/AgentSettings.tsx --fix
```
Expected: no errors

**Step 4: Run frontend tests**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx vitest run src/__tests__/AgentSettings.test.tsx
```
Expected: existing tests still pass

**Step 5: Commit**

```bash
git add frontend/src/pages/AgentSettings.tsx frontend/src/types/agents.ts
git commit -m "feat: add agent_creates_pr toggle to agent settings UI"
```

---

### Task 7: Full suite verification

**Step 1: Run all backend tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -x -v
```
Expected: all pass

**Step 2: Run all frontend tests**

```bash
docker compose -f docker-compose.dev.yml exec frontend npm test
```
Expected: all pass

**Step 3: Full lint + typecheck**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/ --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/ tests/
docker compose -f docker-compose.dev.yml exec backend pyright backend/
```
Expected: no errors

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: agent_creates_pr — agent handles git push and PR creation"
```
