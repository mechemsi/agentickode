# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for SSHService."""

from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from backend.services.workspace.ssh_service import SSHService, SSHTestResult


class TestSSHServiceInit:
    def test_defaults(self):
        svc = SSHService(hostname="10.0.0.1")
        assert svc.hostname == "10.0.0.1"
        assert svc.port == 22
        assert svc.username == "root"

    def test_custom_params(self):
        svc = SSHService(hostname="10.0.0.1", port=2222, username="dev", key_path="/key")
        assert svc.port == 2222
        assert svc.username == "dev"
        assert svc.key_path == "/key"

    def test_tilde_expansion(self):
        svc = SSHService(hostname="10.0.0.1", key_path="~/.ssh/id_ed25519")
        assert "~" not in svc.key_path
        assert svc.key_path.endswith(".ssh/id_ed25519")


class TestForServer:
    def test_creates_from_model(self):
        server = MagicMock()
        server.hostname = "10.0.0.5"
        server.port = 2222
        server.username = "admin"
        server.ssh_key_path = "/custom/key"
        svc = SSHService.for_server(server)
        assert svc.hostname == "10.0.0.5"
        assert svc.port == 2222
        assert svc.username == "admin"
        assert svc.key_path == "/custom/key"

    def test_falls_back_to_default_key(self):
        server = MagicMock()
        server.hostname = "10.0.0.5"
        server.port = 22
        server.username = "root"
        server.ssh_key_path = None
        svc = SSHService.for_server(server)
        assert svc.key_path is not None  # Uses default from settings


class TestTestConnection:
    @pytest.fixture
    def svc(self):
        return SSHService(hostname="10.0.0.1")

    async def test_success(self, svc: SSHService):
        mock_result = MagicMock()
        mock_result.stdout = "ok\n"

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch.object(svc, "_connect", return_value=mock_conn):
            result = await svc.test_connection()
        assert result.success is True
        assert result.latency_ms is not None
        assert result.error is None

    async def test_unexpected_output(self, svc: SSHService):
        mock_result = MagicMock()
        mock_result.stdout = "something else"

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch.object(svc, "_connect", return_value=mock_conn):
            result = await svc.test_connection()
        assert result.success is False
        assert "Unexpected output" in (result.error or "")

    async def test_connection_failure(self, svc: SSHService):
        with patch.object(svc, "_connect", side_effect=ConnectionRefusedError("refused")):
            result = await svc.test_connection()
        assert result.success is False
        assert "refused" in (result.error or "")
        assert result.latency_ms is not None


class TestRunCommand:
    async def test_success(self):
        svc = SSHService(hostname="10.0.0.1")
        mock_result = MagicMock()
        mock_result.stdout = "/usr/bin/claude\n"
        mock_result.stderr = ""
        mock_result.returncode = 0

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch.object(svc, "_connect", return_value=mock_conn):
            stdout, stderr, code = await svc.run_command("command -v claude")
        assert stdout == "/usr/bin/claude\n"
        assert code == 0

    async def test_command_not_found(self):
        svc = SSHService(hostname="10.0.0.1")
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 1

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch.object(svc, "_connect", return_value=mock_conn):
            stdout, stderr, code = await svc.run_command("command -v nonexistent")
        assert code == 1


class TestDeployKey:
    @pytest.fixture
    def svc(self, tmp_path):
        key_file = tmp_path / "id_ed25519"
        key_file.write_text("PRIVATE_KEY")
        pub_file = tmp_path / "id_ed25519.pub"
        pub_file.write_text("ssh-ed25519 AAAA test@host")
        return SSHService(hostname="10.0.0.1", key_path=str(key_file))

    async def test_success(self, svc: SSHService):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        # Mock password connection succeeds, then key auth test succeeds
        test_result = SSHTestResult(success=True, latency_ms=5.0)
        with (
            patch("asyncssh.connect", AsyncMock(return_value=mock_conn)),
            patch.object(svc, "test_connection", AsyncMock(return_value=test_result)),
        ):
            result = await svc.deploy_key("s3cret")

        assert result.success is True
        assert result.latency_ms == 5.0

    async def test_pub_key_not_found(self):
        svc = SSHService(hostname="10.0.0.1", key_path="/nonexistent/key")
        result = await svc.deploy_key("pass")
        assert result.success is False
        assert "Public key not found" in (result.error or "")

    async def test_password_auth_fails(self, svc: SSHService):
        with patch(
            "asyncssh.connect",
            AsyncMock(side_effect=asyncssh.PermissionDenied("bad password")),
        ):
            result = await svc.deploy_key("wrong")
        assert result.success is False
        assert (
            "bad password" in (result.error or "").lower()
            or "denied" in (result.error or "").lower()
        )

    async def test_remote_command_fails(self, svc: SSHService):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "permission denied"

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch("asyncssh.connect", AsyncMock(return_value=mock_conn)):
            result = await svc.deploy_key("pass")
        assert result.success is False
        assert "Failed to deploy key" in (result.error or "")


class TestSSHTestResultDataclass:
    def test_success_result(self):
        r = SSHTestResult(success=True, latency_ms=5.2)
        assert r.success is True
        assert r.latency_ms == 5.2
        assert r.error is None

    def test_failure_result(self):
        r = SSHTestResult(success=False, error="timeout")
        assert r.success is False
        assert r.error == "timeout"