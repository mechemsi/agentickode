# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Service container — holds instantiated service classes for DI."""

from dataclasses import dataclass, field

from backend.services.chromadb_service import ChromaDBService
from backend.services.ollama_service import OllamaService
from backend.services.openhands_service import OpenHandsService
from backend.services.role_resolver import RoleResolver
from backend.services.task_source_updater import TaskSourceUpdater
from backend.services.webhook_callback_service import WebhookCallbackService


@dataclass
class ServiceContainer:
    """Holds all service instances. Passed to worker phases and API handlers."""

    ollama: OllamaService
    openhands: OpenHandsService
    chromadb: ChromaDBService
    role_resolver: RoleResolver
    task_source_updater: TaskSourceUpdater | None = field(default=None)
    webhook_callbacks: WebhookCallbackService | None = field(default=None)