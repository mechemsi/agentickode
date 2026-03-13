# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from pydantic import BaseModel


class ServiceHealth(BaseModel):
    name: str
    status: str  # "ok" | "error"
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    services: list[ServiceHealth]
    worker_running: bool
    active_runs: int
