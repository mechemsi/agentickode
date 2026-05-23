# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for workflow schema models in backend.schemas.workflows."""

from backend.schemas.workflows import PhaseConfig


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
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PhaseConfig(phase_name="x", failure_mode="explode")
