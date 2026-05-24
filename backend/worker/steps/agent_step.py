# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Generic agent step runner — single-shot prompt → response via RoleResolver.

Used by workflow templates whose ``phases[]`` entries have ``kind == "agent"``.
Stays intentionally pure: no DB mutations, no PhaseExecution writes, no
broadcaster calls. The pipeline (Task 1.5) wraps this and records results.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.adapters.cli_adapter import CLIAdapter
from backend.services.container import ServiceContainer
from backend.services.role_resolver import ResolvedRole
from backend.services.workspace.usernames import validate_username
from backend.worker.phases._helpers import get_project_config
from backend.worker.steps.templating import render

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 1800
DEFAULT_ROLE = "coder"
DEFAULT_MODE = "generate"


def _adapter_kwargs(phase_config: dict[str, Any]) -> dict[str, Any]:
    """Build the kwargs forwarded to adapter.generate / adapter.run_task."""
    params = phase_config.get("params") or {}
    kwargs: dict[str, Any] = {
        "timeout": int(phase_config.get("timeout_seconds") or DEFAULT_TIMEOUT),
    }
    if "cli_flags" in phase_config:
        kwargs["cli_flags"] = phase_config["cli_flags"]
    if "environment_vars" in phase_config:
        kwargs["environment_vars"] = phase_config["environment_vars"]
    if "session_id" in params:
        kwargs["session_id"] = params["session_id"]
    if "new_session" in params:
        kwargs["new_session"] = params["new_session"]
    return kwargs


async def run_agent_step(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict[str, Any],
) -> dict[str, Any]:
    """Resolve an agent for the configured role and run a single prompt.

    Returns a dict with ``provider``, ``role``, ``mode``, ``prompt``,
    ``response``, ``session_id`` keys. ``response`` is ``str`` for
    ``mode == "generate"`` and ``dict`` for ``mode == "task"``.
    """
    params = phase_config.get("params") or {}
    raw_prompt: str = params["prompt"]
    role: str = phase_config.get("role") or DEFAULT_ROLE
    mode: str = params.get("mode") or DEFAULT_MODE
    phase_name = phase_config.get("phase_name")

    rendered_prompt = await render(raw_prompt, task_run, session)
    kwargs = _adapter_kwargs(phase_config)
    if "agent_override" in phase_config:
        kwargs["agent_override"] = phase_config["agent_override"]

    resolved: ResolvedRole = await services.role_resolver.resolve(
        role,
        session,
        task_run.workspace_server_id,
        phase_name=phase_name,
    )
    adapter = resolved.adapter

    # Resolve effective run-as: step ``params.run_as`` wins over project
    # override. When the adapter is a ``CLIAdapter`` we temporarily flip
    # its ``worker_user`` for the duration of this call. Other adapters
    # (Ollama HTTP, OpenHands API) don't have a per-call user — they
    # honor whatever the server-level user is.
    #
    # ``CLIAdapter`` later interpolates ``worker_user`` into ``runuser``
    # / ``chown`` commands. We always shell-quote there, but validate
    # the username up front so a misconfiguration fails loudly before
    # any side-effect rather than producing a confusing shell error.
    step_run_as = params.get("run_as")
    if step_run_as:
        run_as: str | None = validate_username(step_run_as, field="step.params.run_as")
    else:
        project = await get_project_config(task_run, session)
        candidate = project.worker_user_override if project else None
        run_as = validate_username(candidate, field="worker_user_override") if candidate else None

    result: dict[str, Any] = {
        "provider": adapter.provider_name,
        "role": role,
        "mode": mode,
        "prompt": rendered_prompt,
        "response": None,
        "session_id": None,
    }

    previous_worker_user: str | None = None
    overrode = False
    if run_as and isinstance(adapter, CLIAdapter):
        previous_worker_user = adapter.worker_user
        adapter.worker_user = run_as
        overrode = True
    try:
        if mode == "task":
            workspace = task_run.workspace_path
            if not workspace:
                raise ValueError(
                    "agent step mode='task' requires task_run.workspace_path to be set"
                )
            response = await adapter.run_task(workspace, rendered_prompt, **kwargs)
            result["response"] = response
            if isinstance(response, dict) and response.get("session_id"):
                result["session_id"] = response["session_id"]
            return result

        # default: generate
        response_text = await adapter.generate(rendered_prompt, **kwargs)
        result["response"] = response_text
        return result
    finally:
        # Always restore the adapter's worker_user so concurrent runs
        # sharing the same adapter instance aren't affected by this step.
        if overrode and isinstance(adapter, CLIAdapter):
            adapter.worker_user = previous_worker_user
