# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace readiness validation — runs dev-toolchain checks on remote workspace."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from backend.services.workspace.readiness_checks import (
    CheckDef,
    detect_project_checks,
    merge_checks,
)
from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.readiness_service")

MAX_OUTPUT_CHARS = 2000
TTL_DAYS = 7


@dataclass
class CheckResult:
    """Result of a single readiness check."""

    name: str
    category: str
    status: str  # pass | fail | skip
    command: str
    output: str
    duration_s: float
    fix_suggestion: str | None = None


@dataclass
class ValidationReport:
    """Full validation result with fix guide."""

    passed: bool
    summary: str
    checks: list[CheckResult] = field(default_factory=list)

    def report_dict(self) -> dict:
        """Build structured fix guide for DB storage."""
        failures = [c for c in self.checks if c.status == "fail"]
        return {
            "summary": self.summary,
            "passed": sum(1 for c in self.checks if c.status == "pass"),
            "failed": len(failures),
            "skipped": sum(1 for c in self.checks if c.status == "skip"),
            "failures": [
                {
                    "name": f.name,
                    "category": f.category,
                    "error_output": f.output[-MAX_OUTPUT_CHARS:],
                    "fix_commands": [f.fix_suggestion] if f.fix_suggestion else [],
                    "explanation": f.fix_suggestion or "No automatic fix available",
                }
                for f in failures
            ],
        }


class WorkspaceReadinessService:
    """Runs dev-toolchain checks on a remote workspace via SSH."""

    def __init__(self, ssh: SSHService, worker_user: str | None = None):
        self._ssh = ssh
        self._worker_user = worker_user

    async def validate(
        self,
        workspace_path: str,
        dev_commands: dict | None = None,
    ) -> ValidationReport:
        """Run all checks on workspace. Collects ALL results (no early abort)."""
        detected = await detect_project_checks(self._ssh, workspace_path, self._worker_user)
        checks_to_run = merge_checks(detected, dev_commands)

        if not checks_to_run:
            return ValidationReport(
                passed=True,
                summary="No checks detected for this project",
                checks=[],
            )

        results: list[CheckResult] = []
        for check_def in checks_to_run:
            result = await self._run_check(check_def, workspace_path)
            results.append(result)
            status_icon = (
                "✓" if result.status == "pass" else "✗" if result.status == "fail" else "—"
            )
            logger.info(
                "[%s] %s: %s (%.1fs)", status_icon, result.name, result.status, result.duration_s
            )

        fail_count = sum(1 for r in results if r.status == "fail")
        total = len(results)
        passed = fail_count == 0

        return ValidationReport(
            passed=passed,
            summary=f"{fail_count} of {total} checks failed"
            if not passed
            else f"All {total} checks passed",
            checks=results,
        )

    async def _run_check(self, check_def: CheckDef, cwd: str) -> CheckResult:
        """Execute a single check via SSH, capture output."""
        cmd = f"cd {cwd} && {check_def.command}"
        start = time.monotonic()
        try:
            if self._worker_user:
                stdout, stderr, exit_code = await self._ssh.run_command_as(
                    self._worker_user, cmd, timeout=check_def.timeout
                )
            else:
                stdout, stderr, exit_code = await self._ssh.run_command(
                    cmd, timeout=check_def.timeout
                )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return CheckResult(
                name=check_def.name,
                category=check_def.category,
                status="fail",
                command=check_def.command,
                output=f"Command error: {exc}"[-MAX_OUTPUT_CHARS:],
                duration_s=round(elapsed, 1),
                fix_suggestion=check_def.fix_suggestion,
            )

        elapsed = time.monotonic() - start
        combined_output = f"{stdout}\n{stderr}".strip()

        return CheckResult(
            name=check_def.name,
            category=check_def.category,
            status="pass" if exit_code == 0 else "fail",
            command=check_def.command,
            output=combined_output[-MAX_OUTPUT_CHARS:],
            duration_s=round(elapsed, 1),
            fix_suggestion=check_def.fix_suggestion if exit_code != 0 else None,
        )


def format_fix_guide(report: ValidationReport) -> str:
    """Format validation report as human-readable text for logs."""
    lines = [
        "=== WORKSPACE READINESS FAILED ===",
        report.summary,
        "",
    ]
    for check in report.checks:
        if check.status != "fail":
            continue
        lines.append(f"FAILED: {check.name} ({check.category})")
        lines.append(f"  Command: {check.command}")
        # Show last few lines of output
        output_lines = check.output.strip().splitlines()
        preview = "\n    ".join(output_lines[-5:])
        lines.append(f"  Output:\n    {preview}")
        if check.fix_suggestion:
            lines.append(f"  Fix: {check.fix_suggestion}")
        lines.append("")

    lines.append("After fixing, restart the run to re-validate.")
    return "\n".join(lines)
