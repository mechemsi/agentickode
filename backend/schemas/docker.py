# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for Docker management endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class DockerContainer(BaseModel):
    id: str
    names: str
    image: str
    status: str
    state: str
    ports: str
    created_at: str | None = None
    size: str | None = None


class DockerImage(BaseModel):
    id: str
    repository: str
    tag: str
    size: str
    created_at: str | None = None


class DockerVolume(BaseModel):
    name: str
    driver: str
    mountpoint: str | None = None


class DockerNetwork(BaseModel):
    id: str
    name: str
    driver: str
    scope: str


class DockerComposeStack(BaseModel):
    name: str
    status: str
    config_files: str | None = None


class DockerOverview(BaseModel):
    containers: list[DockerContainer]
    images: list[DockerImage]
    volumes: list[DockerVolume]
    networks: list[DockerNetwork]
    stacks: list[DockerComposeStack]
    disk_usage: str


class PruneResult(BaseModel):
    output: str


class PruneRequest(BaseModel):
    target: str  # containers | images | volumes | networks | system
    all: bool = False
    include_volumes: bool = False  # for system prune


class ContainerLogsResponse(BaseModel):
    logs: str


class ContainerInspectResponse(BaseModel):
    data: dict
