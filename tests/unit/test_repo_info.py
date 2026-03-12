# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for backend.services.git.repo_info."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.services.git.repo_info import get_default_branch, get_default_branch_via_ssh


def _make_mock_response(status_code: int, body: dict) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = body
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=mock_response,
        )
    else:
        mock_response.raise_for_status = MagicMock()
    return mock_response


def _make_client(response: MagicMock) -> AsyncMock:
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = response
    return mock_client


@pytest.mark.asyncio
async def test_github_success():
    response = _make_mock_response(200, {"default_branch": "main"})
    client = _make_client(response)
    branch = await get_default_branch("github", "acme", "myrepo", client)
    assert branch == "main"
    client.get.assert_awaited_once()
    url = client.get.call_args[0][0]
    assert "api.github.com" in url
    assert "acme/myrepo" in url


@pytest.mark.asyncio
async def test_gitlab_success():
    response = _make_mock_response(200, {"default_branch": "develop"})
    client = _make_client(response)
    branch = await get_default_branch("gitlab", "acme", "myrepo", client)
    assert branch == "develop"
    url = client.get.call_args[0][0]
    assert "acme%2Fmyrepo" in url


@pytest.mark.asyncio
async def test_gitea_success():
    response = _make_mock_response(200, {"default_branch": "master"})
    client = _make_client(response)
    branch = await get_default_branch("gitea", "acme", "myrepo", client)
    assert branch == "master"
    url = client.get.call_args[0][0]
    assert "api/v1/repos/acme/myrepo" in url


@pytest.mark.asyncio
async def test_bitbucket_success():
    response = _make_mock_response(200, {"mainbranch": {"name": "main"}})
    client = _make_client(response)
    branch = await get_default_branch("bitbucket", "acme", "myrepo", client)
    assert branch == "main"
    url = client.get.call_args[0][0]
    assert "2.0/repositories/acme/myrepo" in url


@pytest.mark.asyncio
async def test_unknown_provider_raises_value_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    with pytest.raises(ValueError, match="unknown provider"):
        await get_default_branch("unknown", "acme", "myrepo", client)
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_api_404_raises_http_status_error():
    response = _make_mock_response(404, {"message": "Not Found"})
    client = _make_client(response)
    with pytest.raises(httpx.HTTPStatusError):
        await get_default_branch("github", "acme", "missing-repo", client)


@pytest.mark.asyncio
async def test_api_401_raises_http_status_error():
    response = _make_mock_response(401, {"message": "Unauthorized"})
    client = _make_client(response)
    with pytest.raises(httpx.HTTPStatusError):
        await get_default_branch("github", "acme", "myrepo", client)


# -- SSH-based branch detection --


class TestGetDefaultBranchViaSSH:
    async def test_parses_symref_output(self):
        ssh = AsyncMock()
        ssh.run_command = AsyncMock(
            return_value=("ref: refs/heads/develop\tHEAD\nabc123\tHEAD\n", "", 0)
        )
        branch = await get_default_branch_via_ssh(ssh, "git@github.com:org/repo.git")
        assert branch == "develop"

    async def test_parses_main_branch(self):
        ssh = AsyncMock()
        ssh.run_command = AsyncMock(
            return_value=("ref: refs/heads/main\tHEAD\nabc123\tHEAD\n", "", 0)
        )
        branch = await get_default_branch_via_ssh(ssh, "git@github.com:org/repo.git")
        assert branch == "main"

    async def test_fallback_when_symref_missing(self):
        ssh = AsyncMock()
        ssh.run_command = AsyncMock(return_value=("abc123\tHEAD\n", "", 0))
        branch = await get_default_branch_via_ssh(ssh, "git@github.com:org/repo.git")
        assert branch == "main"

    async def test_raises_on_nonzero_exit(self):
        ssh = AsyncMock()
        ssh.run_command = AsyncMock(return_value=("", "fatal: repository not found", 128))
        with pytest.raises(RuntimeError, match="repository not found"):
            await get_default_branch_via_ssh(ssh, "git@github.com:org/repo.git")

    async def test_raises_on_permission_denied(self):
        ssh = AsyncMock()
        ssh.run_command = AsyncMock(return_value=("", "Permission denied (publickey)", 128))
        with pytest.raises(RuntimeError, match="Permission denied"):
            await get_default_branch_via_ssh(ssh, "git@github.com:org/repo.git")