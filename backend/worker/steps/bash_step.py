# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Generic bash step runner — executes a shell command on the workspace."""

from __future__ import annotations

import logging
import shlex
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.workspace.command_executor import CommandExecutor
from backend.worker.phases._helpers import get_project_config, get_ssh_for_run
from backend.worker.steps.templating import render

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 600


def _wrap_runuser(cmd: str, user: str) -> str:
    """Wrap ``cmd`` so it runs under ``user`` via ``runuser -l``.

    Matches the wrapping pattern used in ``workspace_setup`` and
    ``cli_adapter`` so step-level overrides behave the same as the
    project- and server-level ones.
    """
    return f"runuser -l {shlex.quote(user)} -c {shlex.quote(cmd)}"


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

    # Resolve effective run-as user: step ``params.run_as`` wins over
    # ``ProjectConfig.worker_user_override``. We do *not* fall back to the
    # server's ``worker_user`` here — that's already handled implicitly
    # by the ambient executor user (e.g. the agent adapter wraps once at
    # the boundary). Step-level wrapping is opt-in.
    run_as = params.get("run_as")
    if not run_as:
        project = await get_project_config(task_run, session)
        run_as = project.worker_user_override if project else None
    # Only wrap if we'd actually change user and the executor can drop
    # privileges (running as root). ``runuser`` from a non-root caller
    # typically requires PAM/sudo configuration that isn't safe to
    # assume — fall through and let the OS reject if misconfigured.
    if run_as and run_as != executor.username and executor.username == "root":
        rendered_cmd = _wrap_runuser(rendered_cmd, run_as)

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
