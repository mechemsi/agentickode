# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""FastAPI dependency factories for service injection."""

from backend.services.adapters.factory import AdapterFactory
from backend.services.chromadb_service import ChromaDBService
from backend.services.container import ServiceContainer
from backend.services.http_client import get_http_client
from backend.services.ollama_service import OllamaService
from backend.services.openhands_service import OpenHandsService
from backend.services.role_resolver import RoleResolver
from backend.services.task_source_updater import TaskSourceUpdater
from backend.services.webhook_callback_service import WebhookCallbackService


def get_ollama_service() -> OllamaService:
    return OllamaService(get_http_client())


def get_openhands_service() -> OpenHandsService:
    return OpenHandsService(get_http_client())


def get_chromadb_service() -> ChromaDBService:
    return ChromaDBService(get_http_client())


def get_service_container() -> ServiceContainer:
    client = get_http_client()
    openhands = OpenHandsService(client)
    factory = AdapterFactory(http_client=client, openhands=openhands)
    resolver = RoleResolver(factory=factory, http_client=client)
    return ServiceContainer(
        ollama=OllamaService(client),
        openhands=openhands,
        chromadb=ChromaDBService(client),
        role_resolver=resolver,
        task_source_updater=TaskSourceUpdater(client),
        webhook_callbacks=WebhookCallbackService(client),
    )
