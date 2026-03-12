# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Shared fixtures for integration tests."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_get_default_branch():
    """Patch get_default_branch so integration tests don't hit real provider APIs."""
    with (
        patch(
            "backend.api.projects.get_default_branch",
            new_callable=AsyncMock,
            return_value="main",
        ) as mock_fn,
        patch(
            "backend.api.projects.get_default_branch_via_ssh",
            new_callable=AsyncMock,
            return_value="main",
        ),
    ):
        yield mock_fn