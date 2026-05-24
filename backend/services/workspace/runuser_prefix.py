# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Shared helper: compute a ``runuser -l`` prefix for backend-host commands.

Used by the local terminal (``api/local_terminals``) and the chat path
(``services/chat/agent_process``). When the operator sets a
``worker_user`` on the local platform server, every command the backend
spawns on the host should drop to that user via ``runuser -l``.

Two responsibilities live here so the call sites stay small:

1. **Decide whether to wrap.** No-op when ``worker_user`` is unset,
   matches the current process user, or the backend isn't running as
   root (``runuser`` requires privilege).

2. **Lazily provision the user.** On the local server, the worker user
   typically doesn't exist inside the backend Docker container. We
   ``useradd -m`` idempotently and copy the minimum Claude/git config
   so the agent can authenticate. This mirrors what
   :class:`WorkerUserService.setup` does for remote SSH servers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex

from backend.services.workspace.usernames import validate_username

logger = logging.getLogger("agentickode.runuser_prefix")


async def ensure_local_user(username: str) -> tuple[bool, str]:
    """Idempotently create ``username`` on the local backend host.

    Returns ``(ok, message)``. ``message`` is empty on success or a
    short error otherwise. Safe to call repeatedly.
    """
    safe = shlex.quote(username)
    # ``useradd`` only runs when the user doesn't exist; the leading
    # ``id`` check makes the whole shell line idempotent.
    cmd = f"id -u {safe} >/dev/null 2>&1 || useradd -m -s /bin/bash {safe}"
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr_bytes = await proc.communicate()
    if proc.returncode != 0:
        msg = (stderr_bytes.decode("utf-8", errors="replace") or "").strip()
        logger.warning("useradd %s failed (rc=%d): %s", username, proc.returncode, msg)
        return False, msg or f"useradd failed rc={proc.returncode}"

    # Best-effort copy of Claude / git config so the agent has auth. All
    # fall through silently if the source doesn't exist — the user may
    # be running a non-Claude agent or first-time setup.
    home = f"/home/{username}"
    bootstrap = (
        # Claude config + credentials
        f"cp -fL /root/.claude.json {home}/.claude.json 2>/dev/null; "
        f"mkdir -p {home}/.claude; cp -rnL /root/.claude/. {home}/.claude/ 2>/dev/null; "
        # SSH keys (so git auth works)
        f"mkdir -p {home}/.ssh && chmod 700 {home}/.ssh; "
        f"cp -fL /root/.ssh/id_ed25519 {home}/.ssh/id_ed25519 2>/dev/null; "
        f"cp -fL /root/.ssh/id_ed25519.pub {home}/.ssh/id_ed25519.pub 2>/dev/null; "
        f"chmod 600 {home}/.ssh/id_* 2>/dev/null; "
        # PATH for interactive shells inside tmux
        f"grep -q '\\.local/bin' {home}/.bashrc 2>/dev/null || "
        f"echo 'export PATH=$HOME/.local/bin:$HOME/.local/share/claude/bin:$PATH' "
        f">> {home}/.bashrc; "
        # Ownership — runs as root, so chown afterwards
        f"chown -R {safe}:{safe} {home}/.claude.json {home}/.claude {home}/.ssh {home}/.bashrc "
        f"2>/dev/null || true"
    )
    proc = await asyncio.create_subprocess_shell(bootstrap, stdout=asyncio.subprocess.PIPE)
    await proc.communicate()
    return True, ""


def _current_login() -> str | None:
    """Return the current OS login name without raising on missing tty."""
    try:
        return os.getlogin()
    except OSError:
        return None


async def runuser_prefix(worker_user: str | None) -> str:
    """Compute a ``runuser -l`` command prefix for ``worker_user``.

    Returns an empty string when wrapping isn't needed or possible
    (no user, not root, already the target user). On the wrapping
    path the user is provisioned lazily before returning so the caller
    can interpolate the prefix safely.

    The prefix is suitable for ``f"{prefix}<command>"`` style use when
    ``<command>`` is a single shell-quoted string. Callers that need
    to send a literal command (no shell metacharacters around) can
    wrap the command in ``shlex.quote`` themselves.
    """
    if not worker_user:
        return ""
    validate_username(worker_user, field="worker_user")
    if os.geteuid() != 0:
        return ""
    if _current_login() == worker_user:
        return ""
    await ensure_local_user(worker_user)
    return f"runuser -l {shlex.quote(worker_user)} -c "


def wrap_for_user(cmd: str, prefix: str) -> str:
    """Apply a ``runuser_prefix`` result to ``cmd``.

    ``prefix`` is what :func:`runuser_prefix` returned. When empty,
    ``cmd`` is returned untouched. Otherwise ``cmd`` is shell-quoted
    and appended so ``runuser -l USER -c '<cmd>'`` parses correctly.
    """
    if not prefix:
        return cmd
    return prefix + shlex.quote(cmd)
