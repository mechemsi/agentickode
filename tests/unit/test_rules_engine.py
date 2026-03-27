# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.automation_rules import AutomationRule
from backend.services.rules_engine import AutomationEvent, RulesEngine


def _make_rule(**overrides) -> MagicMock:
    rule = MagicMock(spec=AutomationRule)
    rule.id = overrides.get("id", 1)
    rule.project_id = overrides.get("project_id")
    rule.name = overrides.get("name", "Test rule")
    rule.description = overrides.get("description", "")
    rule.event_source = overrides.get("event_source", "run_event")
    rule.event_filter = overrides.get("event_filter", {"event_type": "run_failed"})
    rule.action_type = overrides.get("action_type", "create_run")
    rule.action_config = overrides.get("action_config", {"title": "Auto-fix"})
    rule.cooldown_seconds = overrides.get("cooldown_seconds", 300)
    rule.last_triggered_at = overrides.get("last_triggered_at")
    rule.trigger_count = overrides.get("trigger_count", 0)
    rule.enabled = overrides.get("enabled", True)
    return rule


class TestRulesEngineMatching:
    def test_matches_event_source_and_type(self):
        engine = RulesEngine()
        rule = _make_rule(event_source="run_event", event_filter={"event_type": "run_failed"})
        event = AutomationEvent(source="run_event", event_type="run_failed")
        assert engine._matches(rule, event) is True

    def test_no_match_wrong_source(self):
        engine = RulesEngine()
        rule = _make_rule(event_source="monitoring")
        event = AutomationEvent(source="run_event", event_type="run_failed")
        assert engine._matches(rule, event) is False

    def test_no_match_wrong_event_type(self):
        engine = RulesEngine()
        rule = _make_rule(event_filter={"event_type": "run_completed"})
        event = AutomationEvent(source="run_event", event_type="run_failed")
        assert engine._matches(rule, event) is False

    def test_matches_with_project_filter(self):
        engine = RulesEngine()
        rule = _make_rule(project_id="myproject", event_filter={"event_type": "run_failed"})
        event = AutomationEvent(source="run_event", event_type="run_failed", project_id="myproject")
        assert engine._matches(rule, event) is True

    def test_no_match_different_project(self):
        engine = RulesEngine()
        rule = _make_rule(project_id="projectA", event_filter={"event_type": "run_failed"})
        event = AutomationEvent(source="run_event", event_type="run_failed", project_id="projectB")
        assert engine._matches(rule, event) is False

    def test_global_rule_matches_any_project(self):
        engine = RulesEngine()
        rule = _make_rule(project_id=None, event_filter={"event_type": "run_failed"})
        event = AutomationEvent(source="run_event", event_type="run_failed", project_id="anything")
        assert engine._matches(rule, event) is True

    def test_matches_data_filter(self):
        engine = RulesEngine()
        rule = _make_rule(event_filter={"event_type": "phase_failed", "phase": "testing"})
        event = AutomationEvent(
            source="run_event",
            event_type="phase_failed",
            data={"phase": "testing"},
        )
        assert engine._matches(rule, event) is True

    def test_no_match_data_filter_mismatch(self):
        engine = RulesEngine()
        rule = _make_rule(event_filter={"event_type": "phase_failed", "phase": "testing"})
        event = AutomationEvent(
            source="run_event",
            event_type="phase_failed",
            data={"phase": "coding"},
        )
        assert engine._matches(rule, event) is False

    def test_empty_filter_matches_source(self):
        engine = RulesEngine()
        rule = _make_rule(event_filter={})
        event = AutomationEvent(source="run_event", event_type="run_completed")
        assert engine._matches(rule, event) is True


class TestCooldown:
    def test_no_last_trigger_passes(self):
        engine = RulesEngine()
        rule = _make_rule(last_triggered_at=None)
        assert engine._check_cooldown(rule) is True

    def test_within_cooldown_fails(self):
        engine = RulesEngine()
        rule = _make_rule(
            cooldown_seconds=300,
            last_triggered_at=datetime.now(UTC) - timedelta(seconds=60),
        )
        assert engine._check_cooldown(rule) is False

    def test_past_cooldown_passes(self):
        engine = RulesEngine()
        rule = _make_rule(
            cooldown_seconds=300,
            last_triggered_at=datetime.now(UTC) - timedelta(seconds=600),
        )
        assert engine._check_cooldown(rule) is True


class TestExecuteAction:
    @pytest.mark.asyncio
    async def test_create_run_action(self):
        engine = RulesEngine()
        rule = _make_rule(
            project_id="test/project",
            action_config={"title": "Auto-fix", "description": "Fix the issue"},
        )
        event = AutomationEvent(source="run_event", event_type="run_failed", run_id=42)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        mock_project = MagicMock()
        mock_project.project_id = "test/project"
        mock_project.repo_owner = "test"
        mock_project.repo_name = "project"
        mock_project.default_branch = "main"
        mock_project.git_provider = "github"
        mock_project.workspace_path = "/workspaces/test"
        mock_project.workspace_config = {}
        mock_project.autonomy_config = {}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "backend.services.rules_engine.ProjectConfigRepository",
                lambda session: MagicMock(get_by_id=AsyncMock(return_value=mock_project)),
            )
            result = await engine.execute(rule, event, mock_session)

        assert result is True
        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.task_source == "automation"
        assert added.title == "Auto-fix"
        assert rule.trigger_count == 1
