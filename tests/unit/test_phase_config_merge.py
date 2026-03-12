# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for per-phase command config merge in _helpers.py."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.worker.phases._helpers import (
    apply_phase_command_overrides,
    get_agent_mode,
    get_agent_settings_kwargs,
    phase_uses_agent,
)

# ---------------------------------------------------------------------------
# get_agent_settings_kwargs
# ---------------------------------------------------------------------------


class TestGetAgentSettingsKwargs:
    def test_no_settings_no_config(self):
        assert get_agent_settings_kwargs(None) == {}

    def test_no_settings_no_config_explicit(self):
        assert get_agent_settings_kwargs(None, None) == {}

    def test_agent_settings_only(self):
        settings = SimpleNamespace(
            cli_flags={"--model": "opus"},
            environment_vars={"OPENAI_KEY": "x"},
            default_timeout=600,
        )
        result = get_agent_settings_kwargs(settings)
        assert result == {
            "cli_flags": {"--model": "opus"},
            "environment_vars": {"OPENAI_KEY": "x"},
            "timeout": 600,
        }

    def test_phase_config_only(self):
        phase = {
            "cli_flags": {"--model": "sonnet"},
            "environment_vars": {"FOO": "bar"},
            "timeout_seconds": 300,
        }
        result = get_agent_settings_kwargs(None, phase)
        assert result == {
            "cli_flags": {"--model": "sonnet"},
            "environment_vars": {"FOO": "bar"},
            "timeout": 300,
        }

    def test_phase_overrides_agent(self):
        settings = SimpleNamespace(
            cli_flags={"--model": "opus", "--verbose": "true"},
            environment_vars={"KEY": "old", "OTHER": "keep"},
            default_timeout=600,
        )
        phase = {
            "cli_flags": {"--model": "sonnet"},
            "environment_vars": {"KEY": "new"},
            "timeout_seconds": 120,
        }
        result = get_agent_settings_kwargs(settings, phase)
        # Phase --model overwrites agent --model; --verbose is kept
        assert result["cli_flags"] == {"--model": "sonnet", "--verbose": "true"}
        # Phase KEY overwrites agent KEY; OTHER is kept
        assert result["environment_vars"] == {"KEY": "new", "OTHER": "keep"}
        # Phase timeout replaces agent timeout
        assert result["timeout"] == 120

    def test_none_phase_values_dont_override(self):
        settings = SimpleNamespace(
            cli_flags={"--model": "opus"},
            environment_vars={"A": "1"},
            default_timeout=600,
        )
        phase = {
            "cli_flags": None,
            "environment_vars": None,
            "timeout_seconds": None,
        }
        result = get_agent_settings_kwargs(settings, phase)
        assert result == {
            "cli_flags": {"--model": "opus"},
            "environment_vars": {"A": "1"},
            "timeout": 600,
        }

    def test_empty_agent_settings_fields(self):
        """Agent settings with None/empty fields produce empty dict."""
        settings = SimpleNamespace(
            cli_flags=None,
            environment_vars=None,
            default_timeout=None,
        )
        assert get_agent_settings_kwargs(settings) == {}

    def test_phase_config_without_new_keys(self):
        """Phase config dict without cli_flags/env/timeout is a no-op."""
        settings = SimpleNamespace(
            cli_flags={"--model": "opus"},
            environment_vars=None,
            default_timeout=None,
        )
        phase = {"phase_name": "coding", "enabled": True}
        result = get_agent_settings_kwargs(settings, phase)
        assert result == {"cli_flags": {"--model": "opus"}}


# ---------------------------------------------------------------------------
# apply_phase_command_overrides
# ---------------------------------------------------------------------------


class TestApplyPhaseCommandOverrides:
    def test_none_phase_config(self):
        adapter = MagicMock()
        apply_phase_command_overrides(adapter, None)
        adapter.apply_command_overrides.assert_not_called()

    def test_no_command_templates_key(self):
        adapter = MagicMock()
        apply_phase_command_overrides(adapter, {"phase_name": "coding"})
        adapter.apply_command_overrides.assert_not_called()

    def test_null_command_templates(self):
        adapter = MagicMock()
        apply_phase_command_overrides(adapter, {"command_templates": None})
        adapter.apply_command_overrides.assert_not_called()

    def test_cli_adapter_gets_overrides(self):
        """CLIAdapter receives command_templates via apply_command_overrides."""
        adapter = MagicMock(spec=["apply_command_overrides"])
        # Make isinstance check pass by setting __class__
        from backend.services.adapters.cli_adapter import CLIAdapter

        adapter.__class__ = CLIAdapter
        overrides = {"task": "custom-cmd {workspace} {instruction_file}"}
        apply_phase_command_overrides(adapter, {"command_templates": overrides})
        adapter.apply_command_overrides.assert_called_once_with(overrides)

    def test_non_cli_adapter_ignored(self):
        """Non-CLIAdapter adapters are silently ignored."""
        adapter = MagicMock(spec=["generate", "run_task"])
        apply_phase_command_overrides(adapter, {"command_templates": {"task": "something"}})
        # isinstance(adapter, CLIAdapter) is False for MagicMock,
        # so apply_command_overrides should never be called
        assert not adapter.method_calls


# ---------------------------------------------------------------------------
# phase_uses_agent
# ---------------------------------------------------------------------------


class TestPhaseUsesAgent:
    def test_explicit_true(self):
        assert phase_uses_agent("workspace_setup", {"uses_agent": True}) is True

    def test_explicit_false(self):
        assert phase_uses_agent("coding", {"uses_agent": False}) is False

    def test_none_falls_to_default_agent_phase(self):
        """phases in _DEFAULT_PHASE_ROLES default to True."""
        assert phase_uses_agent("planning", {"uses_agent": None}) is True
        assert phase_uses_agent("coding", {"uses_agent": None}) is True
        assert phase_uses_agent("reviewing", {"uses_agent": None}) is True

    def test_none_falls_to_default_non_agent_phase(self):
        """Phases NOT in _DEFAULT_PHASE_ROLES default to False."""
        assert phase_uses_agent("workspace_setup", {"uses_agent": None}) is False
        assert phase_uses_agent("init", {"uses_agent": None}) is False
        assert phase_uses_agent("testing", {"uses_agent": None}) is False
        assert phase_uses_agent("finalization", {"uses_agent": None}) is False

    def test_none_phase_config(self):
        """None phase_config falls to default."""
        assert phase_uses_agent("coding", None) is True
        assert phase_uses_agent("testing", None) is False

    def test_missing_key_falls_to_default(self):
        """phase_config dict without uses_agent key falls to default."""
        assert phase_uses_agent("coding", {"enabled": True}) is True
        assert phase_uses_agent("init", {"enabled": True}) is False


# ---------------------------------------------------------------------------
# get_agent_mode
# ---------------------------------------------------------------------------


class TestGetAgentMode:
    def test_explicit_generate(self):
        assert get_agent_mode("coding", {"agent_mode": "generate"}) == "generate"

    def test_explicit_task(self):
        assert get_agent_mode("planning", {"agent_mode": "task"}) == "task"

    def test_none_planning_default(self):
        """None agent_mode returns 'generate' for planning."""
        assert get_agent_mode("planning", {"agent_mode": None}) == "generate"

    def test_none_coding_default(self):
        """None agent_mode returns 'task' for coding."""
        assert get_agent_mode("coding", {"agent_mode": None}) == "task"

    def test_none_reviewing_default(self):
        """None agent_mode returns 'generate' for reviewing."""
        assert get_agent_mode("reviewing", {"agent_mode": None}) == "generate"

    def test_none_unknown_phase(self):
        """None agent_mode returns 'generate' for unknown phases."""
        assert get_agent_mode("testing", {"agent_mode": None}) == "generate"
        assert get_agent_mode("finalization", {}) == "generate"

    def test_none_config(self):
        """None phase_config returns default for each phase."""
        assert get_agent_mode("planning", None) == "generate"
        assert get_agent_mode("coding", None) == "task"
        assert get_agent_mode("reviewing", None) == "generate"

    def test_invalid_mode_falls_to_default(self):
        """Invalid mode values are ignored, falls to default."""
        assert get_agent_mode("coding", {"agent_mode": "invalid"}) == "task"
        assert get_agent_mode("planning", {"agent_mode": ""}) == "generate"