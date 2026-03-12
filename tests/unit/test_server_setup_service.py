# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for ServerSetupService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models import WorkspaceServer
from backend.services.workspace.setup_service import SETUP_STEPS, ServerSetupService, _step_entry


class TestStepEntry:
    def test_default_pending(self):
        entry = _step_entry()
        assert entry["status"] == "pending"
        assert entry["error"] is None

    def test_failed_with_error(self):
        entry = _step_entry("failed", "something broke")
        assert entry["status"] == "failed"
        assert entry["error"] == "something broke"

    def test_has_timestamp(self):
        entry = _step_entry("running")
        assert "timestamp" in entry


class TestFindResumeStep:
    def test_all_completed(self):
        log = {step: _step_entry("completed") for step in SETUP_STEPS}
        assert ServerSetupService._find_resume_step(log) == len(SETUP_STEPS)

    def test_first_step_pending(self):
        log = {step: _step_entry() for step in SETUP_STEPS}
        assert ServerSetupService._find_resume_step(log) == 0

    def test_resumes_from_failed(self):
        log = {}
        for i, step in enumerate(SETUP_STEPS):
            if i < 3:
                log[step] = _step_entry("completed")
            elif i == 3:
                log[step] = _step_entry("failed", "err")
            else:
                log[step] = _step_entry()
        assert ServerSetupService._find_resume_step(log) == 3

    def test_empty_log(self):
        assert ServerSetupService._find_resume_step({}) == 0


class TestExecuteStep:
    """Test individual setup steps via _execute_step."""

    @pytest.fixture()
    def mock_session_factory(self, db_session):
        """Create a mock session factory wrapping the real test session."""

        class FakeCtx:
            def __init__(self, session):
                self._session = session

            async def __aenter__(self):
                return self._session

            async def __aexit__(self, *args):
                pass

        return MagicMock(return_value=FakeCtx(db_session))

    @pytest.fixture()
    async def server(self, db_session) -> WorkspaceServer:
        """Create a test workspace server."""
        srv = WorkspaceServer(
            name="test-server",
            hostname="10.10.50.25",
            port=22,
            username="root",
            ssh_key_path="/app/.ssh/id_ed25519",
            worker_user="coder",
            status="setting_up",
        )
        db_session.add(srv)
        await db_session.commit()
        await db_session.refresh(srv)
        return srv

    async def test_ssh_test_step_success(self, server, mock_session_factory):
        svc = ServerSetupService(mock_session_factory)

        mock_result = MagicMock(success=True)
        with patch("backend.services.workspace.setup_service.SSHService") as mock_ssh_cls:
            mock_ssh = AsyncMock()
            mock_ssh.test_connection.return_value = mock_result
            mock_ssh_cls.for_server.return_value = mock_ssh

            await svc._execute_step(server.id, "ssh_test")

    async def test_ssh_test_step_failure(self, server, mock_session_factory):
        svc = ServerSetupService(mock_session_factory)

        mock_result = MagicMock(success=False, error="Connection refused")
        with patch("backend.services.workspace.setup_service.SSHService") as mock_ssh_cls:
            mock_ssh = AsyncMock()
            mock_ssh.test_connection.return_value = mock_result
            mock_ssh_cls.for_server.return_value = mock_ssh

            with pytest.raises(RuntimeError, match="SSH connection failed"):
                await svc._execute_step(server.id, "ssh_test")

    async def test_create_worker_user_step(self, server, mock_session_factory):
        svc = ServerSetupService(mock_session_factory)

        mock_info = MagicMock(exists=True, error=None)
        with (
            patch("backend.services.workspace.setup_service.SSHService") as mock_ssh_cls,
            patch("backend.services.workspace.setup_service.WorkerUserService") as mock_wus_cls,
        ):
            mock_ssh_cls.for_server.return_value = AsyncMock()
            mock_wus = mock_wus_cls.return_value
            # check_status returns "not exists" so setup() is called
            mock_wus.check_status = AsyncMock(return_value=MagicMock(exists=False))
            mock_wus.setup = AsyncMock(return_value=mock_info)

            await svc._execute_step(server.id, "create_worker_user")

            mock_wus.check_status.assert_called_once_with("coder")
            mock_wus.setup.assert_called_once_with("coder")

    async def test_create_worker_user_already_exists(self, server, mock_session_factory):
        svc = ServerSetupService(mock_session_factory)

        mock_info = MagicMock(exists=True, error=None)
        with (
            patch("backend.services.workspace.setup_service.SSHService") as mock_ssh_cls,
            patch("backend.services.workspace.setup_service.WorkerUserService") as mock_wus_cls,
        ):
            mock_ssh_cls.for_server.return_value = AsyncMock()
            mock_wus = mock_wus_cls.return_value
            # check_status returns "exists" — setup() should NOT be called
            mock_wus.check_status = AsyncMock(return_value=mock_info)
            mock_wus.setup = AsyncMock()

            await svc._execute_step(server.id, "create_worker_user")

            mock_wus.check_status.assert_called_once_with("coder")
            mock_wus.setup.assert_not_called()

    async def test_mark_online_step(self, server, mock_session_factory):
        svc = ServerSetupService(mock_session_factory)

        with patch("backend.services.workspace.setup_service.SSHService") as mock_ssh_cls:
            mock_ssh_cls.for_server.return_value = AsyncMock()
            await svc._execute_step(server.id, "mark_online")

        # The mark_online step updates the server within its own session context


class TestSetupSteps:
    def test_all_steps_defined(self):
        """Verify the step list hasn't been accidentally modified."""
        assert len(SETUP_STEPS) == 9
        assert SETUP_STEPS[0] == "ssh_test"
        assert SETUP_STEPS[1] == "install_system_deps"
        assert SETUP_STEPS[-1] == "mark_online"
        assert "install_agents" in SETUP_STEPS
        assert "generate_ssh_key" in SETUP_STEPS