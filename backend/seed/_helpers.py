# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Shared helpers for seed modules."""

from backend.services.adapters.cli_commands import AGENT_COMMANDS


def commands_for(agent_name: str) -> dict:
    """Extract string command templates from AGENT_COMMANDS (skip booleans)."""
    return {k: v for k, v in AGENT_COMMANDS[agent_name].items() if isinstance(v, str)}
