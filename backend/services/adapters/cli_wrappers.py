# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI command wrapping helpers for non-root user execution and flag injection."""

from __future__ import annotations

import shlex

from backend.services.adapters.cli_commands import _CODER_USER, _ENSURE_CODER_USER


def wrap_non_root(cmd: str, workspace: str, instruction_file: str) -> str:
    """Wrap command to run as non-root 'coder' user.

    - Creates user idempotently
    - Copies root's CLI binaries into coder's PATH
    - Copies Claude config/API keys
    - Sets workspace + instruction file ownership
    - Explicitly sets PATH for coder's shell
    - Runs actual command via runuser
    """
    ownership = (
        f"chown -R {_CODER_USER}:{_CODER_USER} {shlex.quote(workspace)}; "
        f"chown {_CODER_USER}:{_CODER_USER} {shlex.quote(instruction_file)}; "
    )
    # Git safe.directory so coder can operate in root-owned parent dirs
    git_safe = (
        f"runuser -u {_CODER_USER} -- "
        f"git config --global --add safe.directory {shlex.quote(workspace)}; "
    )
    # Explicitly set PATH inside coder's shell to include coder's bin dirs
    coder_path = (
        f"/home/{_CODER_USER}/.local/bin"
        f":/home/{_CODER_USER}/.claude/bin"
        ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )
    inner_cmd = f"export PATH={shlex.quote(coder_path)} && {cmd}"
    run = f"runuser -u {_CODER_USER} -- bash -c {shlex.quote(inner_cmd)}"
    return f"{_ENSURE_CODER_USER}{ownership}{git_safe}{run}"


def wrap_for_user(cmd: str, workspace: str, instruction_file: str, username: str) -> str:
    """Wrap command to run as a pre-configured worker user.

    Unlike wrap_non_root, this does NOT create the user or copy binaries
    inline — that's handled by WorkerUserService.setup() ahead of time.
    """
    ownership = (
        f"chown -R {username}:{username} {shlex.quote(workspace)}; "
        f"chown {username}:{username} {shlex.quote(instruction_file)}; "
    )
    git_safe = (
        f"runuser -u {username} -- "
        f"git config --global --add safe.directory {shlex.quote(workspace)}; "
    )
    user_path = (
        f"/home/{username}/.local/bin"
        f":/home/{username}/.claude/bin"
        ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )
    inner_cmd = f"export PATH={shlex.quote(user_path)} && {cmd}"
    run = f"runuser -u {username} -- bash -c {shlex.quote(inner_cmd)}"
    return f"{ownership}{git_safe}{run}"


def wrap_generate_for_user(cmd: str, prompt_file: str, username: str) -> str:
    """Wrap a generate command to run as a non-root user.

    Simpler than wrap_for_user — no workspace ownership needed, just
    prompt file access and correct PATH/user for session continuity.
    """
    ownership = f"chown {username}:{username} {shlex.quote(prompt_file)}; "
    user_path = (
        f"/home/{username}/.local/bin"
        f":/home/{username}/.claude/bin"
        ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )
    inner_cmd = f"export PATH={shlex.quote(user_path)} && {cmd}"
    run = f"runuser -u {username} -- bash -c {shlex.quote(inner_cmd)}"
    return f"{ownership}{run}"


def apply_cli_flags(cmd: str, cli_flags: dict) -> str:
    """Append extra CLI flags from AgentSettings to the command."""
    for flag, value in cli_flags.items():
        if value is True:
            cmd += f" {flag}"
        elif value:
            cmd += f" {flag} {value}"
    return cmd


def apply_env_vars(cmd: str, env_vars: dict) -> str:
    """Prepend environment variable exports to the command."""
    exports = " ".join(
        f"{shlex.quote(k)}={shlex.quote(str(v))}" for k, v in env_vars.items() if k.strip()
    )
    if exports:
        return f"export {exports} && {cmd}"
    return cmd
