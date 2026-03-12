# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI agent command templates and non-root user constants."""

from __future__ import annotations

_CODER_USER = "coder"

# Shell snippet that creates a non-root user and copies config/credentials.
# Runs idempotently — safe to call on every invocation.
# NOTE: Agents are installed directly as the worker user, so no binary
# copying is needed here. This is a lightweight fallback for wrap_non_root.
_ENSURE_CODER_USER = f"""
id -u {_CODER_USER} &>/dev/null || useradd -m -s /bin/bash {_CODER_USER}
mkdir -p /home/{_CODER_USER}/.local/bin
# Copy Claude config + API keys (merge, don't destroy session data)
cp -fL /root/.claude.json /home/{_CODER_USER}/.claude.json 2>/dev/null || true
mkdir -p /home/{_CODER_USER}/.claude
cp -rnL /root/.claude/* /home/{_CODER_USER}/.claude/ 2>/dev/null || true
# Ensure common git hosts are in known_hosts
mkdir -p /root/.ssh
ssh-keyscan -t ed25519 github.com gitlab.com bitbucket.org >> /root/.ssh/known_hosts 2>/dev/null || true
sort -u -o /root/.ssh/known_hosts /root/.ssh/known_hosts 2>/dev/null || true
# Copy SSH keys so coder has same git provider access as root
mkdir -p /home/{_CODER_USER}/.ssh && chmod 700 /home/{_CODER_USER}/.ssh
cp -fL /root/.ssh/id_ed25519 /home/{_CODER_USER}/.ssh/id_ed25519 2>/dev/null || true
cp -fL /root/.ssh/id_ed25519.pub /home/{_CODER_USER}/.ssh/id_ed25519.pub 2>/dev/null || true
cp -fL /root/.ssh/id_rsa /home/{_CODER_USER}/.ssh/id_rsa 2>/dev/null || true
cp -fL /root/.ssh/id_rsa.pub /home/{_CODER_USER}/.ssh/id_rsa.pub 2>/dev/null || true
test -f /root/.ssh/known_hosts && cp -fL /root/.ssh/known_hosts /home/{_CODER_USER}/.ssh/known_hosts 2>/dev/null || true
chmod 600 /home/{_CODER_USER}/.ssh/id_* 2>/dev/null || true
chown -R {_CODER_USER}:{_CODER_USER} /home/{_CODER_USER}
"""

# Default agent command templates — used as fallback when DB has no overrides.
# Keys:
#   generate        — prompt-based generation (no workspace)
#   task            — fresh task run in workspace
#   task_continue   — resume a previous session (only for agents with supports_session=True)
#   check           — availability check command
#   supports_session — whether the agent supports session continuity
AGENT_COMMANDS: dict[str, dict[str, str | bool]] = {
    "claude": {
        "generate": "cat {prompt_file} | claude --print --output-format json",
        "generate_session_start": "cd {workspace} && cat {prompt_file} | claude --print --output-format json --session-id {session_id}",
        "generate_continue": "cd {workspace} && cat {prompt_file} | claude --print --output-format json --resume {session_id}",
        "task": "cd {workspace} && cat {instruction_file} | claude --dangerously-skip-permissions --print --output-format json",
        "task_session_start": "cd {workspace} && cat {instruction_file} | claude --dangerously-skip-permissions --print --output-format json --session-id {session_id}",
        "task_continue": "cd {workspace} && cat {instruction_file} | claude --dangerously-skip-permissions --print --output-format json --resume {session_id}",
        "check": "command -v claude",
        "supports_session": True,
    },
    "codex": {
        "generate": "codex --quiet -p {prompt_file}",
        "task": "cd {workspace} && codex -p {instruction_file}",
        "check": "command -v codex",
        "supports_session": False,
    },
    "aider": {
        "generate": "aider --yes --no-git --message-file {prompt_file}",
        "task": "cd {workspace} && aider --yes --message-file {instruction_file}",
        "check": "command -v aider",
        "supports_session": False,
    },
    "opencode": {
        "generate": "cat {prompt_file} | opencode",
        "task": "cd {workspace} && opencode -p {instruction_file}",
        "check": "command -v opencode",
        "supports_session": False,
    },
    "gemini": {
        "generate": "cat {prompt_file} | gemini",
        "task": "cd {workspace} && gemini -p {instruction_file}",
        "check": "command -v gemini",
        "supports_session": False,
    },
    "kimi": {
        "generate": "cat {prompt_file} | kimi",
        "task": "cd {workspace} && kimi -p {instruction_file}",
        "check": "command -v kimi",
        "supports_session": False,
    },
    "copilot": {
        "generate": 'copilot -p "$(cat {prompt_file})"',
        "task": 'cd {workspace} && copilot --autopilot --yolo -p "$(cat {instruction_file})"',
        "check": "command -v copilot",
        "supports_session": False,
    },
}