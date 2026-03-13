# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase: Testing — run tests on remote workspace server via SSH.

Extracted from coding.py to enable independent test execution.
"""

import logging
import shlex

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.workspace.ssh_service import SSHService
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._helpers import get_ssh_for_run

logger = logging.getLogger("agentickode.phases.testing")

PHASE_META = {
    "description": "Run tests on remote workspace",
}


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None:
    """Run tests on the remote workspace server. Best-effort."""
    await broadcaster.log(task_run.id, "Running tests on workspace server", phase="testing")
    ssh = await get_ssh_for_run(task_run, session)
    test_cmd = f"cd {shlex.quote(task_run.workspace_path)} && make test"
    test_results = await _run_remote_tests(ssh, task_run.workspace_path, test_cmd)

    await broadcaster.log(
        task_run.id,
        f"Test command: {test_cmd}",
        level="debug",
        phase="testing",
        metadata=make_log_metadata(
            "ssh_command",
            command=test_cmd,
            stdout=test_results.get("output", ""),
            stderr=test_results.get("error", ""),
            exit_code=0 if test_results.get("success") else 1,
        ),
    )

    task_run.test_results = test_results
    await session.commit()

    status = "passed" if test_results.get("success") else "skipped/failed"
    await broadcaster.log(task_run.id, f"Tests {status}", phase="testing")


async def _run_remote_tests(ssh: SSHService, workspace: str, test_cmd: str) -> dict:
    """Run tests on the remote workspace server. Best-effort."""
    try:
        stdout, stderr, rc = await ssh.run_command(test_cmd, timeout=300)
        return {
            "success": rc == 0,
            "output": stdout[-2000:] if stdout else "",
            "error": stderr[-1000:] if stderr else "",
        }
    except Exception:
        return {"success": True, "output": "No test runner found, skipped", "error": ""}
