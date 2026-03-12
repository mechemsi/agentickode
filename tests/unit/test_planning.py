# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for planning phase."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.models import PhaseExecution
from backend.services.role_resolver import ResolvedRole
from backend.worker.phases import planning


class TestPlanning:
    async def test_calls_adapter_and_stores_result(self, db_session, make_task_run, mock_services):
        run = make_task_run(planning_result={"context_docs": ["some context"]})
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        mock_adapter.generate.return_value = (
            '{"subtasks": [{"id": 1, "title": "Do X"}], "estimated_complexity": "simple"}'
        )
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.planning.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.planning.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await planning.run(run, db_session, mock_services)

        mock_services.role_resolver.resolve.assert_called_once_with(
            "planner", db_session, None, phase_name="planning"
        )
        mock_adapter.generate.assert_called_once()
        assert run.planning_result["subtasks"][0]["title"] == "Do X"
        assert run.planning_result["estimated_complexity"] == "simple"

    async def test_empty_context(self, db_session, make_task_run, mock_services):
        run = make_task_run(planning_result=None)
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        mock_adapter.generate.return_value = '{"subtasks": [], "estimated_complexity": "simple"}'
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.planning.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.planning.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await planning.run(run, db_session, mock_services)

        assert run.planning_result["subtasks"] == []

    async def test_json_extract_failure_raises(self, db_session, make_task_run, mock_services):
        run = make_task_run()
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        mock_adapter.generate.return_value = "This is not JSON at all"
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.planning.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.planning.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            import pytest

            with pytest.raises(ValueError):
                await planning.run(run, db_session, mock_services)

    async def test_resolves_with_workspace_server_id(
        self, db_session, make_task_run, mock_services
    ):
        """When project has workspace_server_id, it's passed to resolver."""
        run = make_task_run(planning_result={"context_docs": []})
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws-01"
        mock_adapter.generate.return_value = '{"subtasks": [], "estimated_complexity": "simple"}'
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.planning.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.planning.get_workspace_server_id",
                new=AsyncMock(return_value=42),
            ),
        ):
            await planning.run(run, db_session, mock_services)

        mock_services.role_resolver.resolve.assert_called_once_with(
            "planner", db_session, 42, phase_name="planning"
        )

    async def test_plan_review_enabled_sets_coding_trigger(
        self, db_session, make_task_run, mock_services
    ):
        """When enable_plan_review=True and subtasks exist, coding phase gets wait_for_trigger."""
        run = make_task_run(planning_result={"context_docs": ["ctx"]})
        db_session.add(run)
        await db_session.flush()

        # Create a coding PhaseExecution row
        coding_pe = PhaseExecution(
            run_id=run.id,
            phase_name="coding",
            order_index=3,
            trigger_mode="auto",
        )
        db_session.add(coding_pe)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        mock_adapter.generate.return_value = (
            '{"subtasks": [{"id": 1, "title": "Do X"}], "estimated_complexity": "simple"}'
        )
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        phase_config = {"params": {"enable_plan_review": True}}
        mock_broadcaster = MagicMock(log=AsyncMock(), event=AsyncMock())

        with (
            patch("backend.worker.phases.planning.broadcaster", new=mock_broadcaster),
            patch(
                "backend.worker.phases.planning.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await planning.run(run, db_session, mock_services, phase_config=phase_config)

        await db_session.refresh(coding_pe)
        assert coding_pe.trigger_mode == "wait_for_trigger"
        # Verify plan_review_requested event was emitted
        event_calls = [
            c for c in mock_broadcaster.event.call_args_list if c[0][1] == "plan_review_requested"
        ]
        assert len(event_calls) == 1

    async def test_plan_review_disabled_by_default(self, db_session, make_task_run, mock_services):
        """By default (no enable_plan_review), coding phase trigger_mode stays auto."""
        run = make_task_run(planning_result={"context_docs": []})
        db_session.add(run)
        await db_session.flush()

        coding_pe = PhaseExecution(
            run_id=run.id,
            phase_name="coding",
            order_index=3,
            trigger_mode="auto",
        )
        db_session.add(coding_pe)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        mock_adapter.generate.return_value = (
            '{"subtasks": [{"id": 1, "title": "Do X"}], "estimated_complexity": "simple"}'
        )
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.planning.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.planning.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await planning.run(run, db_session, mock_services)

        await db_session.refresh(coding_pe)
        assert coding_pe.trigger_mode == "auto"