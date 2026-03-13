# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Base protocol for notification providers."""

from typing import Protocol

import httpx


class NotificationProvider(Protocol):
    """Interface that all notification providers must implement."""

    async def send(self, message: str, config: dict, client: httpx.AsyncClient) -> None:
        """Send a notification message."""
        ...

    async def test(self, config: dict, client: httpx.AsyncClient) -> tuple[bool, str | None]:
        """Send a test notification. Returns (success, error_message)."""
        ...
