# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Validation for OS usernames before they flow into shell commands.

``worker_user`` (server default), ``ProjectConfig.worker_user_override``,
and ``step.params.run_as`` all eventually land in `runuser -l <name>` or
`chown <name>:<name>` invocations. We always shell-quote them at the
boundary, but defense-in-depth: a username that passes ``shlex.quote``
can still cause confusing failures (or be valid POSIX but not POSIX-safe
for our pipeline). Reject anything outside the conservative pattern up
front so a misconfiguration fails loudly at the API/edit boundary rather
than silently mid-run.

The allowlist matches the conservative interpretation of POSIX 3.437
(NAME_REGEX) used by ``useradd -E`` / Debian's ``adduser --conf``:

    [a-z_][a-z0-9_-]*[$]?

with a 32-char cap. Uppercase letters are intentionally rejected — Linux
allows them in usernames, but no mainstream distro creates them by
default and they're a frequent source of subtle bugs in scripts.
"""

from __future__ import annotations

import re

# Matches a single POSIX-safe username. 32 chars is the LOGIN_NAME_MAX
# minimum guaranteed by ``sysconf(_SC_LOGIN_NAME_MAX)`` on Linux; some
# systems allow more but accepting beyond that risks downstream breakage.
_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}\$?$")


class UsernameError(ValueError):
    """Raised when a configured worker user / run_as value is unsafe."""


def validate_username(name: str, *, field: str = "worker_user") -> str:
    """Return ``name`` if it matches the safe pattern; else raise.

    ``field`` is woven into the error message so the caller (project
    form, step editor, server-create) can be identified by the user
    fixing it.
    """
    if not isinstance(name, str) or not name:
        raise UsernameError(f"{field} must be a non-empty string")
    if not _USERNAME_RE.match(name):
        raise UsernameError(
            f"{field}={name!r} is not a valid POSIX username " "(allowed: [a-z_][a-z0-9_-]{0,31}$?)"
        )
    return name
