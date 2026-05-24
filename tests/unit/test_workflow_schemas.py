# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for workflow schema models in backend.schemas.workflows."""

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.schemas.workflows import (
    IssueEventTrigger,
    LabelTrigger,
    ManualTrigger,
    PhaseConfig,
    PrEventTrigger,
    ScheduleTrigger,
    WorkflowTemplateCreate,
    WorkflowTriggerRule,
)

_TriggerAdapter = TypeAdapter(WorkflowTriggerRule)


def test_phase_config_defaults_kind_to_legacy_phase():
    cfg = PhaseConfig(phase_name="planning")
    assert cfg.kind == "legacy_phase"


def test_phase_config_accepts_bash_kind():
    cfg = PhaseConfig(
        phase_name="run-make-build",
        kind="bash",
        params={"command": "make build"},
    )
    assert cfg.kind == "bash"


def test_phase_config_accepts_agent_kind():
    cfg = PhaseConfig(
        phase_name="fix-issue",
        kind="agent",
        params={"prompt": "Fix issue {{run.title}}"},
    )
    assert cfg.kind == "agent"


def test_phase_config_rejects_unknown_kind():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PhaseConfig(phase_name="x", kind="not-a-kind")


def test_phase_config_defaults_failure_mode_to_fail():
    cfg = PhaseConfig(phase_name="x")
    assert cfg.failure_mode == "fail"


def test_phase_config_accepts_skip_failure_mode():
    cfg = PhaseConfig(phase_name="x", kind="bash", failure_mode="skip")
    assert cfg.failure_mode == "skip"


def test_phase_config_rejects_unknown_failure_mode():
    with pytest.raises(ValidationError):
        PhaseConfig(phase_name="x", failure_mode="explode")


class TestWorkflowTriggerRule:
    def test_label_trigger_round_trips(self):
        rule = _TriggerAdapter.validate_python(
            {"type": "label", "source": "github", "match_any": ["ai-task"]}
        )
        assert isinstance(rule, LabelTrigger)
        assert rule.source == "github"
        dumped = _TriggerAdapter.dump_python(rule)
        assert dumped["type"] == "label"

    def test_issue_event_trigger_round_trips(self):
        rule = _TriggerAdapter.validate_python(
            {"type": "issue_event", "source": "gitea", "action": "opened"}
        )
        assert isinstance(rule, IssueEventTrigger)
        assert rule.action == "opened"
        assert rule.label_filter == []

    def test_pr_event_trigger_round_trips(self):
        rule = _TriggerAdapter.validate_python(
            {
                "type": "pr_event",
                "source": "github",
                "action": "review_requested",
                "label_filter": ["needs-bot"],
            }
        )
        assert isinstance(rule, PrEventTrigger)
        assert rule.action == "review_requested"
        assert rule.label_filter == ["needs-bot"]

    def test_schedule_trigger_round_trips(self):
        rule = _TriggerAdapter.validate_python({"type": "schedule", "cron": "*/5 * * * *"})
        assert isinstance(rule, ScheduleTrigger)
        assert rule.cron == "*/5 * * * *"

    def test_manual_trigger_round_trips(self):
        rule = _TriggerAdapter.validate_python({"type": "manual"})
        assert isinstance(rule, ManualTrigger)

    def test_rejects_unknown_trigger_type(self):
        with pytest.raises(ValidationError):
            _TriggerAdapter.validate_python({"type": "not-a-trigger"})

    def test_label_trigger_rejects_invalid_source(self):
        with pytest.raises(ValidationError):
            _TriggerAdapter.validate_python({"type": "label", "source": "twitter"})

    def test_workflow_template_create_accepts_triggers(self):
        tpl = WorkflowTemplateCreate(
            name="x",
            triggers=[
                {"type": "label", "match_any": ["ai-task"]},
                {"type": "schedule", "cron": "0 * * * *"},
            ],
        )
        assert len(tpl.triggers) == 2
        assert isinstance(tpl.triggers[0], LabelTrigger)
        assert isinstance(tpl.triggers[1], ScheduleTrigger)

    def test_workflow_template_create_defaults_to_empty_triggers(self):
        tpl = WorkflowTemplateCreate(name="x")
        assert tpl.triggers == []
