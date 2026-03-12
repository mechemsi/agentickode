# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for session continuity in the coding phase."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.role_resolver import ResolvedRole
from backend.worker.phases import coding
from backend.worker.phases.coding import (
    _build_continuation_prompt,
    _get_previous_session_id,
)


class TestBuildContinuationPrompt:
    def test_produces_short_prompt(self):
        subtask = {
            "title": "Add error handling",
            "description": "Wrap the API call in try/except",
            "files_likely_affected": ["api.py", "utils.py"],
        }
        prompt = _build_continuation_prompt(subtask)
        assert "Add error handling" in prompt
        assert "Wrap the API call in try/except" in prompt
        assert "api.py" in prompt
        assert "Continue from where you left off" in prompt

    def test_continuation_prompt_shorter_than_full_prompt(self):
        subtask = {
            "title": "Fix bug",
            "description": "Fix the auth bug",
            "files_likely_affected": ["auth.py"],
        }
        continuation = _build_continuation_prompt(subtask)
        full = coding._build_coding_prompt(subtask, ["a.py", "b.py"], coding.FALLBACK_USER_TEMPLATE)
        # Continuation prompt should be meaningfully shorter
        assert len(continuation) < len(full)

    def test_works_with_empty_files_list(self):
        subtask = {"title": "T", "description": "D", "files_likely_affected": []}
        prompt = _build_continuation_prompt(subtask)
        assert "T" in prompt
        assert "D" in prompt

    def test_works_with_missing_keys(self):
        # Should not raise even when keys are missing
        prompt = _build_continuation_prompt({})
        assert isinstance(prompt, str)


class TestGetPreviousSessionId:
    def test_returns_none_when_no_planning_result(self, make_task_run):
        run = make_task_run(planning_result=None)
        assert _get_previous_session_id(run) is None

    def test_returns_none_when_no_session_id_in_planning(self, make_task_run):
        run = make_task_run(planning_result={"subtasks": []})
        assert _get_previous_session_id(run) is None

    def test_returns_session_id_from_planning_result(self, make_task_run):
        run = make_task_run(planning_result={"subtasks": [], "session_id": "abc-123"})
        assert _get_previous_session_id(run) == "abc-123"

    def test_ignores_non_string_session_id(self, make_task_run):
        run = make_task_run(planning_result={"session_id": 12345})
        assert _get_previous_session_id(run) is None


class TestCodingSessionGeneration:
    async def test_session_id_generated_for_session_capable_agent(
        self, db_session, make_task_run, mock_services
    ):
        run = make_task_run(
            planning_result={
                "subtasks": [
                    {"title": "T1", "description": "D1", "files_likely_affected": ["a.py"]}
                ]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws-01"
        mock_adapter.supports_session = True  # Claude supports sessions
        mock_adapter.run_task.return_value = {
            "files_changed": ["a.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
            "command": "claude ...",
            "session_id": None,
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await coding.run(run, db_session, mock_services)

        # Session-capable agent: run_task should have been called with a session_id
        call_kwargs = mock_adapter.run_task.call_args.kwargs
        assert call_kwargs.get("session_id") is not None
        assert isinstance(call_kwargs["session_id"], str)

    async def test_no_session_for_non_session_agent(self, db_session, make_task_run, mock_services):
        run = make_task_run(
            planning_result={
                "subtasks": [{"title": "T1", "description": "D1", "files_likely_affected": []}]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/aider@ws-01"
        mock_adapter.supports_session = False  # Aider doesn't support sessions
        mock_adapter.run_task.return_value = {
            "files_changed": ["a.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
            "command": "aider ...",
            "session_id": None,
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await coding.run(run, db_session, mock_services)

        # Non-session agent: session_id should be None
        call_kwargs = mock_adapter.run_task.call_args.kwargs
        assert call_kwargs.get("session_id") is None

    async def test_session_id_stored_in_coding_results(
        self, db_session, make_task_run, mock_services
    ):
        run = make_task_run(
            planning_result={
                "subtasks": [
                    {"title": "T1", "description": "D1", "files_likely_affected": ["a.py"]}
                ]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws-01"
        mock_adapter.supports_session = True
        mock_adapter.run_task.return_value = {
            "files_changed": ["a.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
            "command": "claude ...",
            "session_id": None,
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await coding.run(run, db_session, mock_services)

        # Session ID should be persisted in coding_results for reviewing phase to pick up
        assert run.coding_results is not None
        assert "session_id" in run.coding_results
        assert isinstance(run.coding_results["session_id"], str)

    async def test_session_id_not_stored_for_non_session_agent(
        self, db_session, make_task_run, mock_services
    ):
        run = make_task_run(
            planning_result={
                "subtasks": [{"title": "T1", "description": "D1", "files_likely_affected": []}]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/codex@ws-01"
        mock_adapter.supports_session = False
        mock_adapter.run_task.return_value = {
            "files_changed": ["b.py"],
            "exit_code": 0,
            "output": "",
            "stderr": "",
            "command": "codex ...",
            "session_id": None,
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await coding.run(run, db_session, mock_services)

        # Non-session agent: no session_id in coding_results
        assert "session_id" not in (run.coding_results or {})

    async def test_continuation_prompt_used_for_subsequent_subtasks(
        self, db_session, make_task_run, mock_services
    ):
        run = make_task_run(
            planning_result={
                "subtasks": [
                    {"title": "T1", "description": "D1", "files_likely_affected": ["a.py"]},
                    {"title": "T2", "description": "D2", "files_likely_affected": ["b.py"]},
                ]
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws-01"
        mock_adapter.supports_session = True
        mock_adapter.run_task.return_value = {
            "files_changed": ["a.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
            "command": "claude ...",
            "session_id": None,
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.worker.phases.coding._auto_commit_changes",
                new=AsyncMock(return_value=False),
            ),
        ):
            await coding.run(
                run,
                db_session,
                mock_services,
                phase_config={"params": {"subtask_mode": "separate"}},
            )

        assert mock_adapter.run_task.call_count == 2

        # First call: full prompt (no continuation template text)
        first_call_kwargs = mock_adapter.run_task.call_args_list[0].kwargs
        first_instruction = first_call_kwargs["instruction"]
        assert "Continue from where you left off" not in first_instruction

        # Second call: continuation prompt
        second_call_kwargs = mock_adapter.run_task.call_args_list[1].kwargs
        second_instruction = second_call_kwargs["instruction"]
        assert "Continue from where you left off" in second_instruction

    async def test_continues_from_previous_phase_session(
        self, db_session, make_task_run, mock_services
    ):
        """Coding phase picks up session_id from planning_result."""
        prior_session = "prior-session-from-planning"
        run = make_task_run(
            planning_result={
                "subtasks": [{"title": "T1", "description": "D1", "files_likely_affected": []}],
                "session_id": prior_session,
            }
        )
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws-01"
        mock_adapter.supports_session = True
        mock_adapter.run_task.return_value = {
            "files_changed": ["a.py"],
            "exit_code": 0,
            "output": "done",
            "stderr": "",
            "command": "claude ...",
            "session_id": None,
        }
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.coding.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.coding.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await coding.run(run, db_session, mock_services)

        # Should use the prior session_id from planning
        call_kwargs = mock_adapter.run_task.call_args.kwargs
        assert call_kwargs.get("session_id") == prior_session
        # Inherited session must NOT use new_session=True (would cause
        # "Session ID already in use" error since planning already created it)
        assert call_kwargs.get("new_session") is False