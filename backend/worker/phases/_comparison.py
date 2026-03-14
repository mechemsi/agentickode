# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""A/B comparison mode — run subtasks with two agents on separate branches."""

import logging
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, PhaseExecution, TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._coding_utils import (
    FALLBACK_SYSTEM_PROMPT,
    FALLBACK_USER_TEMPLATE,
    build_coding_prompt,
)
from backend.worker.phases._helpers import (
    ensure_agent_ready,
    get_ssh_for_run,
    get_token_usage,
)
from backend.worker.phases._prompt_resolver import resolve_prompts

logger = logging.getLogger("agentickode.phases.comparison")


async def run_comparison(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict,
    subtasks: list[dict],
    phase_exec: PhaseExecution | None,
    ws_id: int | None,
) -> None:
    """Run subtasks with two agents on separate branches, store side-by-side results."""
    comparison_cfg = phase_config.get("params", {}).get("comparison", {})
    agents: list[str] = comparison_cfg.get("agents", [])
    if len(agents) < 2:
        raise ValueError("comparison.agents must list at least 2 agent names")

    agent_a_name, agent_b_name = agents[0], agents[1]
    run_id = task_run.id

    ssh = await get_ssh_for_run(task_run, session)
    git = RemoteGitOps(ssh)
    workspace = task_run.workspace_path

    # Record base commit
    head_result = await git.run_git(["rev-parse", "HEAD"], cwd=workspace)
    base_commit = head_result.stdout.strip()

    await broadcaster.log(
        run_id,
        f"A/B comparison: {agent_a_name} vs {agent_b_name} (base: {base_commit[:8]})",
        phase="coding",
    )

    comparison_results: dict = {
        "comparison_mode": True,
        "base_commit": base_commit,
        "agents": {},
        "winner": None,
    }

    for label, agent_name in [("a", agent_a_name), ("b", agent_b_name)]:
        branch = f"compare-{agent_name}-{run_id}"
        await broadcaster.log(
            run_id,
            f"[Agent {label.upper()}] Starting {agent_name} on branch {branch}",
            phase="coding",
        )

        # Create comparison branch from base commit
        await git.run_git(["checkout", "-B", branch, base_commit], cwd=workspace)

        # Resolve this specific agent
        resolved = await services.role_resolver.resolve(
            agent_name, session, ws_id, phase_name="coding"
        )
        adapter = resolved.adapter
        config = resolved.role_config

        async def _log(msg: str, level: str = "info") -> None:
            await broadcaster.log(run_id, msg, level=level, phase="coding")

        await ensure_agent_ready(adapter, log_fn=_log, agent_settings=resolved.agent_settings)

        system_prompt, user_template, extra_params, _project_env = await resolve_prompts(
            config, adapter, session, FALLBACK_SYSTEM_PROMPT, FALLBACK_USER_TEMPLATE
        )

        agent_results: list[dict] = []
        invocation_ids: list[int] = []
        total_cost = 0.0
        total_duration = 0.0
        previous_changes: list[str] = []

        for i, subtask in enumerate(subtasks):
            title = subtask.get("title", f"Subtask {i + 1}")
            coding_prompt = build_coding_prompt(subtask, previous_changes, user_template)

            await broadcaster.log(
                run_id,
                f"[Agent {label.upper()}] Subtask {i + 1}/{len(subtasks)}: {title}",
                phase="coding",
            )

            invocation = AgentInvocation(
                run_id=run_id,
                phase_execution_id=phase_exec.id if phase_exec else None,
                workspace_server_id=ws_id,
                agent_name=adapter.provider_name,
                phase_name="coding",
                subtask_index=i,
                subtask_title=title,
                prompt_text=coding_prompt,
                system_prompt_text=system_prompt,
                prompt_chars=len(coding_prompt),
                status="running",
                started_at=datetime.now(UTC),
                metadata_={"comparison_label": label, "comparison_branch": branch},
            )
            session.add(invocation)
            await session.flush()

            async def _log_ssh(msg: str) -> None:
                await broadcaster.log(run_id, f"  {msg}", level="debug", phase="coding")

            t0 = time.monotonic()
            result = await adapter.run_task(
                workspace=workspace,
                instruction=coding_prompt,
                system_prompt=system_prompt,
                max_iterations=20,
                log_fn=_log_ssh,
                **extra_params,
            )
            elapsed = time.monotonic() - t0

            files_changed = result.get("files_changed", [])
            exit_code = result.get("exit_code", "?")
            agent_output = result.get("output", "")
            agent_stderr = result.get("stderr", "")

            invocation.response_text = agent_output
            invocation.response_chars = len(agent_output)
            invocation.exit_code = exit_code if isinstance(exit_code, int) else None
            invocation.files_changed = files_changed
            invocation.duration_seconds = round(elapsed, 1)
            invocation.completed_at = datetime.now(UTC)
            invocation.status = "success" if exit_code == 0 else "failed"
            if exit_code != 0:
                invocation.error_message = agent_stderr[:1000] if agent_stderr else None
            tokens_in, tokens_out, cost, token_source = get_token_usage(
                adapter, adapter.provider_name, invocation.prompt_chars, len(agent_output)
            )
            invocation.estimated_tokens_in = tokens_in
            invocation.estimated_tokens_out = tokens_out
            invocation.estimated_cost_usd = cost
            if invocation.metadata_ is None:
                invocation.metadata_ = {}
            invocation.metadata_["token_source"] = token_source  # type: ignore[index]
            await session.flush()

            total_cost += cost
            total_duration += elapsed
            invocation_ids.append(invocation.id)
            previous_changes.extend(files_changed)

            agent_results.append(
                {
                    "subtask_title": title,
                    "files_changed": files_changed,
                    "exit_code": exit_code,
                }
            )

        comparison_results["agents"][label] = {
            "agent_name": agent_name,
            "branch": branch,
            "results": agent_results,
            "total_cost_usd": round(total_cost, 6),
            "total_duration_seconds": round(total_duration, 1),
            "invocation_ids": invocation_ids,
        }

        # Reset workspace back to base commit for next agent
        await git.run_git(["checkout", base_commit], cwd=workspace)
        await broadcaster.log(
            run_id,
            f"[Agent {label.upper()}] Done — {len(agent_results)} subtask(s), "
            f"cost=${total_cost:.4f}, time={total_duration:.0f}s",
            phase="coding",
        )

    task_run.coding_results = comparison_results
    await session.commit()

    await broadcaster.log(
        run_id,
        "A/B comparison complete — awaiting winner selection",
        phase="coding",
    )
