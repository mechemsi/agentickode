# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Generic bash step runner — executes a shell command on the workspace."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.workspace.command_executor import CommandExecutor
from backend.worker.phases._helpers import get_ssh_for_run
from backend.worker.steps.templating import render

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 600


async def run_bash_step(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict[str, Any],
    *,
    executor: CommandExecutor | None = None,
) -> dict[str, Any]:
    """Render and execute a bash command on the task's workspace.

    Returns a dict with ``command``, ``stdout``, ``stderr``, ``exit_code``. On
    non-zero exit, behavior depends on ``phase_config["failure_mode"]``:
    ``"fail"`` (default) raises ``RuntimeError``; ``"skip"`` returns the dict
    with ``skipped=True`` so the pipeline can continue.
    """
    params = phase_config.get("params") or {}
    raw_cmd = params["command"]
    rendered_cmd = await render(raw_cmd, task_run, session)

    timeout = int(phase_config.get("timeout_seconds") or DEFAULT_TIMEOUT)
    failure_mode = phase_config.get("failure_mode", "fail")

    if executor is None:
        executor = await get_ssh_for_run(task_run, session)

    stdout, stderr, rc = await executor.run_command(rendered_cmd, timeout=timeout)
    result: dict[str, Any] = {
        "command": rendered_cmd,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": rc,
    }
    if rc != 0:
        if failure_mode == "skip":
            logger.warning(
                "bash step exited rc=%s; failure_mode=skip, continuing. stderr=%r", rc, stderr
            )
            result["skipped"] = True
            return result
        raise RuntimeError(f"bash step failed (rc={rc}): {stderr or stdout}")
    return result
