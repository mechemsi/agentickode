# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for workspace readiness validation service."""

from unittest.mock import AsyncMock, MagicMock

from backend.services.workspace.readiness_checks import (
    CheckDef,
    detect_project_checks,
    merge_checks,
)
from backend.services.workspace.readiness_service import (
    WorkspaceReadinessService,
    format_fix_guide,
)


def _mock_ssh(run_command_side_effect=None):
    ssh = MagicMock()
    if run_command_side_effect:
        ssh.run_command = AsyncMock(side_effect=run_command_side_effect)
    else:
        ssh.run_command = AsyncMock(return_value=("", "", 0))
    ssh.run_command_as = AsyncMock(return_value=("", "", 0))
    return ssh


class TestDetectProjectChecks:
    async def test_detects_node_project(self):
        ssh = _mock_ssh()
        # First call: marker detection returns package.json found
        ssh.run_command = AsyncMock(return_value=("FOUND:package.json", "", 0))
        # Second call for npm scripts detection (empty scripts)
        ssh.run_command.side_effect = [
            ("FOUND:package.json", "", 0),
            ("build,test,lint", "", 0),
        ]
        checks = await detect_project_checks(ssh, "/workspace/proj")
        names = [c.name for c in checks]
        assert "node_runtime" in names
        assert "npm_pkg_manager" in names
        assert "npm_dependencies" in names

    async def test_detects_python_project(self):
        ssh = _mock_ssh()
        ssh.run_command = AsyncMock(return_value=("FOUND:pyproject.toml", "", 0))
        checks = await detect_project_checks(ssh, "/workspace/proj")
        names = [c.name for c in checks]
        assert "python_runtime" in names
        assert "pip_pkg_manager" in names

    async def test_detects_precommit(self):
        ssh = _mock_ssh()
        ssh.run_command = AsyncMock(return_value=("FOUND:.pre-commit-config.yaml", "", 0))
        checks = await detect_project_checks(ssh, "/workspace/proj")
        names = [c.name for c in checks]
        assert "precommit_tool" in names
        assert "precommit_run" in names

    async def test_no_markers_returns_empty(self):
        ssh = _mock_ssh()
        ssh.run_command = AsyncMock(return_value=("", "", 0))
        checks = await detect_project_checks(ssh, "/workspace/proj")
        assert checks == []

    async def test_worker_user_uses_run_command_as(self):
        ssh = _mock_ssh()
        ssh.run_command_as = AsyncMock(return_value=("", "", 0))
        await detect_project_checks(ssh, "/workspace/proj", worker_user="coder")
        ssh.run_command_as.assert_called_once()


class TestMergeChecks:
    def test_no_overrides_returns_detected(self):
        detected = [CheckDef("node_runtime", "runtime", "node --version")]
        result = merge_checks(detected, None)
        assert result == detected

    def test_explicit_build_overrides_detected(self):
        detected = [
            CheckDef("node_runtime", "runtime", "node --version"),
            CheckDef("npm_build", "build", "npm run build"),
        ]
        dev_commands = {"build_cmd": "make build"}
        result = merge_checks(detected, dev_commands)
        names = [c.name for c in result]
        assert "npm_build" not in names
        assert "explicit_build" in names
        build = next(c for c in result if c.name == "explicit_build")
        assert build.command == "make build"

    def test_explicit_precommit_overrides_hooks(self):
        detected = [CheckDef("precommit_run", "hooks", "pre-commit run --all-files")]
        dev_commands = {"precommit_cmd": "make lint"}
        result = merge_checks(detected, dev_commands)
        names = [c.name for c in result]
        assert "precommit_run" not in names
        assert "explicit_hooks" in names

    def test_custom_checks_appended(self):
        detected = [CheckDef("node_runtime", "runtime", "node --version")]
        dev_commands = {
            "custom_checks": [
                {"name": "typecheck", "cmd": "npx tsc --noEmit", "fix": "npm i typescript"}
            ]
        }
        result = merge_checks(detected, dev_commands)
        custom = next(c for c in result if c.name == "typecheck")
        assert custom.category == "custom"
        assert custom.command == "npx tsc --noEmit"
        assert custom.fix_suggestion == "npm i typescript"


class TestWorkspaceReadinessService:
    async def test_all_checks_pass(self):
        ssh = _mock_ssh()
        # Marker detection: no markers found → empty checks
        ssh.run_command = AsyncMock(return_value=("", "", 0))
        svc = WorkspaceReadinessService(ssh)
        result = await svc.validate("/workspace/proj")
        assert result.passed is True
        assert result.checks == []

    async def test_collects_all_failures(self):
        ssh = _mock_ssh()
        # Detection returns package.json
        call_count = 0

        async def side_effect(cmd, timeout=30):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Marker detection
                return ("FOUND:package.json", "", 0)
            if "node -e" in cmd:
                # npm scripts detection
                return ("", "", 0)
            if "node --version" in cmd:
                return ("", "node: command not found", 1)
            if "npm --version" in cmd:
                return ("", "npm: command not found", 1)
            if "npm ci" in cmd:
                return ("", "npm: command not found", 1)
            return ("ok", "", 0)

        ssh.run_command = AsyncMock(side_effect=side_effect)
        svc = WorkspaceReadinessService(ssh)
        result = await svc.validate("/workspace/proj")
        assert result.passed is False
        # All 3 checks should have been attempted (not early abort)
        assert len(result.checks) >= 3
        fail_count = sum(1 for c in result.checks if c.status == "fail")
        assert fail_count >= 2

    async def test_report_dict_structure(self):
        ssh = _mock_ssh()
        ssh.run_command = AsyncMock(return_value=("FOUND:go.mod", "", 0))
        svc = WorkspaceReadinessService(ssh)

        # Make go checks fail
        call_count = 0

        async def side_effect(cmd, timeout=30):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("FOUND:go.mod", "", 0)
            return ("error output", "some error", 1)

        ssh.run_command = AsyncMock(side_effect=side_effect)
        result = await svc.validate("/workspace/proj")
        report = result.report_dict()

        assert "summary" in report
        assert "failures" in report
        assert isinstance(report["failures"], list)
        for f in report["failures"]:
            assert "name" in f
            assert "fix_commands" in f

    async def test_worker_user_commands(self):
        ssh = _mock_ssh()
        ssh.run_command_as = AsyncMock(return_value=("", "", 0))
        svc = WorkspaceReadinessService(ssh, worker_user="coder")
        await svc.validate("/workspace/proj")
        # Should use run_command_as for marker detection
        ssh.run_command_as.assert_called()

    async def test_check_timeout_handled(self):
        ssh = _mock_ssh()

        async def marker_then_timeout(cmd, timeout=30):
            if "test -f" in cmd:
                return ("FOUND:go.mod", "", 0)
            raise TimeoutError("SSH command timed out")

        ssh.run_command = AsyncMock(side_effect=marker_then_timeout)
        svc = WorkspaceReadinessService(ssh)
        result = await svc.validate("/workspace/proj")
        assert result.passed is False
        assert any(
            "error" in c.output.lower() or "timeout" in c.output.lower()
            for c in result.checks
            if c.status == "fail"
        )


class TestFormatFixGuide:
    def test_formats_failures(self):
        from backend.services.workspace.readiness_service import CheckResult, ValidationReport

        report = ValidationReport(
            passed=False,
            summary="2 of 3 checks failed",
            checks=[
                CheckResult("node_runtime", "runtime", "pass", "node --version", "v20.0.0", 0.1),
                CheckResult(
                    "npm_deps",
                    "dependencies",
                    "fail",
                    "npm ci",
                    "ERR! Missing",
                    5.0,
                    "Run: npm install",
                ),
                CheckResult(
                    "precommit",
                    "hooks",
                    "fail",
                    "pre-commit run",
                    "not found",
                    0.5,
                    "pip install pre-commit",
                ),
            ],
        )
        text = format_fix_guide(report)
        assert "WORKSPACE READINESS FAILED" in text
        assert "npm_deps" in text
        assert "precommit" in text
        assert "npm install" in text
        assert "pip install pre-commit" in text
        assert "node_runtime" not in text  # passed, should not be in guide
