# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unified role adapter interfaces and implementations."""

from backend.services.adapters.cli_adapter import CLIAdapter
from backend.services.adapters.factory import AdapterFactory
from backend.services.adapters.ollama_adapter import OllamaAdapter
from backend.services.adapters.openhands_adapter import OpenHandsAdapter
from backend.services.adapters.protocol import RoleAdapter

__all__ = [
    "AdapterFactory",
    "CLIAdapter",
    "OllamaAdapter",
    "OpenHandsAdapter",
    "RoleAdapter",
]