# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""HTTP helpers for CLI commands."""

from __future__ import annotations

import click
import httpx

from backend.cli.output import error

# Reusable client with reasonable timeouts
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _base_url() -> str:
    ctx = click.get_current_context()
    return ctx.obj["url"]


def get(path: str, **params) -> dict | list:
    """GET request to the platform API."""
    url = f"{_base_url()}/api{path}"
    try:
        resp = httpx.get(url, params=params, timeout=_TIMEOUT)
    except httpx.ConnectError:
        error(f"Cannot connect to {_base_url()} — is the platform running?")
    if resp.status_code >= 400:
        error(f"API error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def post(path: str, json_data: dict | None = None) -> dict:
    """POST request to the platform API."""
    url = f"{_base_url()}/api{path}"
    try:
        resp = httpx.post(url, json=json_data or {}, timeout=_TIMEOUT)
    except httpx.ConnectError:
        error(f"Cannot connect to {_base_url()} — is the platform running?")
    if resp.status_code >= 400:
        error(f"API error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def put(path: str, json_data: dict | None = None) -> dict:
    """PUT request to the platform API."""
    url = f"{_base_url()}/api{path}"
    try:
        resp = httpx.put(url, json=json_data or {}, timeout=_TIMEOUT)
    except httpx.ConnectError:
        error(f"Cannot connect to {_base_url()} — is the platform running?")
    if resp.status_code >= 400:
        error(f"API error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def delete(path: str) -> None:
    """DELETE request to the platform API."""
    url = f"{_base_url()}/api{path}"
    try:
        resp = httpx.delete(url, timeout=_TIMEOUT)
    except httpx.ConnectError:
        error(f"Cannot connect to {_base_url()} — is the platform running?")
    if resp.status_code >= 400:
        error(f"API error {resp.status_code}: {resp.text[:200]}")


def stream_sse(path: str):
    """Stream SSE events from the platform API. Yields parsed data strings."""
    url = f"{_base_url()}/api{path}"
    try:
        with httpx.stream("GET", url, timeout=httpx.Timeout(None, connect=10.0)) as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    yield line[6:]
                elif line.startswith(": keepalive"):
                    continue
    except httpx.ConnectError:
        error(f"Cannot connect to {_base_url()}")
    except KeyboardInterrupt:
        pass
