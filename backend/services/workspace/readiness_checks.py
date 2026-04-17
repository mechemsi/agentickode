# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Check definitions and auto-detection for workspace readiness validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.workspace.command_executor import CommandExecutor

logger = logging.getLogger("agentickode.readiness_checks")


@dataclass
class CheckDef:
    """A single readiness check definition."""

    name: str
    category: str  # runtime | package_manager | dependencies | hooks | build | test | lint | custom
    command: str
    fix_suggestion: str | None = None
    timeout: int = 120


# Marker file → list of checks to add
_MARKER_CHECKS: dict[str, list[CheckDef]] = {
    "package.json": [
        CheckDef(
            "node_runtime",
            "runtime",
            "node --version",
            "Install Node.js: curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && apt-get install -y nodejs",
        ),
        CheckDef(
            "npm_pkg_manager", "package_manager", "npm --version", "npm is bundled with Node.js"
        ),
        CheckDef("npm_dependencies", "dependencies", "npm ci --ignore-scripts", "Run: npm install"),
    ],
    "pyproject.toml": [
        CheckDef(
            "python_runtime",
            "runtime",
            "python3 --version",
            "Install Python: apt-get install -y python3 python3-pip",
        ),
        CheckDef(
            "pip_pkg_manager",
            "package_manager",
            "pip --version || pip3 --version",
            "Install pip: apt-get install -y python3-pip",
        ),
    ],
    "requirements.txt": [
        CheckDef(
            "python_runtime",
            "runtime",
            "python3 --version",
            "Install Python: apt-get install -y python3 python3-pip",
        ),
        CheckDef(
            "pip_pkg_manager",
            "package_manager",
            "pip --version || pip3 --version",
            "Install pip: apt-get install -y python3-pip",
        ),
        CheckDef(
            "pip_dependencies",
            "dependencies",
            "pip install -r requirements.txt --dry-run",
            "Run: pip install -r requirements.txt",
        ),
    ],
    "go.mod": [
        CheckDef("go_runtime", "runtime", "go version", "Install Go: https://go.dev/doc/install"),
        CheckDef("go_dependencies", "dependencies", "go mod download", "Run: go mod download"),
    ],
    "Cargo.toml": [
        CheckDef(
            "rust_runtime",
            "runtime",
            "rustc --version",
            "Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
        ),
        CheckDef("cargo_pkg_manager", "package_manager", "cargo --version", "Bundled with Rust"),
    ],
    ".pre-commit-config.yaml": [
        CheckDef(
            "precommit_tool", "hooks", "pre-commit --version", "Install: pip install pre-commit"
        ),
        CheckDef(
            "precommit_run",
            "hooks",
            "pre-commit run --all-files",
            "Run: pre-commit install && pre-commit run --all-files",
            timeout=300,
        ),
    ],
    "Makefile": [
        CheckDef(
            "make_tool", "runtime", "make --version", "Install: apt-get install -y build-essential"
        ),
    ],
}


async def detect_project_checks(
    ssh: CommandExecutor,
    workspace_path: str,
    worker_user: str | None = None,
) -> list[CheckDef]:
    """Auto-detect readiness checks from marker files in the workspace."""
    # Build a single command that tests all marker files at once
    markers = list(_MARKER_CHECKS.keys())
    test_cmds = " && ".join(f'test -f "{workspace_path}/{m}" && echo "FOUND:{m}"' for m in markers)
    # Use `|| true` so the command always succeeds even if files don't exist
    full_cmd = f"cd {workspace_path} && {{ {test_cmds}; true; }}"

    if worker_user:
        stdout, _, _ = await ssh.run_command_as(worker_user, full_cmd, timeout=15)
    else:
        stdout, _, _ = await ssh.run_command(full_cmd, timeout=15)

    found_markers = set()
    for line in stdout.strip().splitlines():
        if line.startswith("FOUND:"):
            found_markers.add(line[6:])

    # Collect checks, dedup by name (first occurrence wins)
    checks: list[CheckDef] = []
    seen_names: set[str] = set()
    for marker in markers:
        if marker in found_markers:
            for check in _MARKER_CHECKS[marker]:
                if check.name not in seen_names:
                    checks.append(check)
                    seen_names.add(check.name)

    # Also detect npm build/lint/test scripts if package.json found
    if "package.json" in found_markers:
        checks.extend(await _detect_npm_scripts(ssh, workspace_path, worker_user))

    logger.info(
        "Detected %d checks from %d marker files in %s",
        len(checks),
        len(found_markers),
        workspace_path,
    )
    return checks


async def _detect_npm_scripts(
    ssh: CommandExecutor, workspace_path: str, worker_user: str | None
) -> list[CheckDef]:
    """Detect available npm scripts (build, test, lint) from package.json."""
    cmd = f"cd {workspace_path} && node -e \"const p=require('./package.json'); console.log(Object.keys(p.scripts||{{}}).join(','))\""
    try:
        if worker_user:
            stdout, _, rc = await ssh.run_command_as(worker_user, cmd, timeout=10)
        else:
            stdout, _, rc = await ssh.run_command(cmd, timeout=10)
        if rc != 0:
            return []
    except Exception:
        return []

    scripts = set(stdout.strip().split(","))
    extra: list[CheckDef] = []
    if "build" in scripts:
        extra.append(CheckDef("npm_build", "build", "npm run build", "Fix build errors"))
    if "test" in scripts:
        extra.append(CheckDef("npm_test", "test", "npm test", "Fix failing tests"))
    if "lint" in scripts:
        extra.append(CheckDef("npm_lint", "lint", "npm run lint", "Fix lint errors"))
    return extra


def merge_checks(detected: list[CheckDef], dev_commands: dict | None) -> list[CheckDef]:
    """Merge auto-detected checks with explicit dev_commands overrides.

    Explicit commands replace auto-detected checks of the same category.
    Custom checks are appended at the end.
    """
    if not dev_commands:
        return detected

    # Map of category → explicit command
    overrides: dict[str, str] = {}
    override_fixes: dict[str, str | None] = {}
    for key in ("build_cmd", "test_cmd", "lint_cmd", "precommit_cmd"):
        if key in dev_commands:
            cat = key.replace("_cmd", "")
            if cat == "precommit":
                cat = "hooks"
            overrides[cat] = dev_commands[key]
            override_fixes[cat] = None

    # Filter detected: keep if category not overridden
    result = [c for c in detected if c.category not in overrides]

    # Add overrides
    for cat, cmd in overrides.items():
        result.append(CheckDef(f"explicit_{cat}", cat, cmd, override_fixes.get(cat)))

    # Add custom checks
    for custom in dev_commands.get("custom_checks", []):
        result.append(
            CheckDef(
                custom["name"],
                "custom",
                custom["cmd"],
                custom.get("fix"),
                timeout=custom.get("timeout", 120),
            )
        )

    return result
