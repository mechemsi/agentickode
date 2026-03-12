# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for get_auth_url helper (SSH-first, HTTPS-fallback)."""

from unittest.mock import AsyncMock, patch

from backend.services.git import KeyInfo
from backend.worker.phases._helpers import get_auth_url


class TestGetAuthUrl:
    async def test_uses_ssh_when_key_exists(self):
        mock_ssh = AsyncMock()
        with patch("backend.worker.phases._helpers.GitAccessService") as mock_gas_cls:
            mock_gas = mock_gas_cls.return_value
            mock_gas.get_public_key = AsyncMock(
                return_value=KeyInfo(has_key=True, public_key="ssh-ed25519 AAA", key_type="ed25519")
            )
            url, method = await get_auth_url("https://github.com/org/repo.git", "github", mock_ssh)
        assert method == "ssh"
        assert url == "git@github.com:org/repo.git"

    async def test_falls_back_to_https_when_no_key(self):
        mock_ssh = AsyncMock()
        with (
            patch("backend.worker.phases._helpers.GitAccessService") as mock_gas_cls,
            patch("backend.worker.phases._helpers.git_ops") as mock_git_ops,
        ):
            mock_gas = mock_gas_cls.return_value
            mock_gas.get_public_key = AsyncMock(return_value=KeyInfo(has_key=False))
            mock_git_ops.inject_git_credentials.return_value = (
                "https://token@github.com/org/repo.git"
            )
            mock_git_ops.to_ssh_url.return_value = None  # won't be called but for safety

            url, method = await get_auth_url("https://github.com/org/repo.git", "github", mock_ssh)
        assert method == "https"
        assert url == "https://token@github.com/org/repo.git"

    async def test_falls_back_to_https_when_url_not_convertible(self):
        mock_ssh = AsyncMock()
        with (
            patch("backend.worker.phases._helpers.GitAccessService") as mock_gas_cls,
            patch("backend.worker.phases._helpers.git_ops") as mock_git_ops,
        ):
            mock_gas = mock_gas_cls.return_value
            mock_gas.get_public_key = AsyncMock(
                return_value=KeyInfo(has_key=True, public_key="ssh-ed25519 AAA", key_type="ed25519")
            )
            mock_git_ops.to_ssh_url.return_value = None  # e.g. non-HTTPS URL
            mock_git_ops.inject_git_credentials.return_value = "https://token@gitea/repo.git"

            url, method = await get_auth_url("http://gitea/org/repo.git", "gitea", mock_ssh)
        assert method == "https"