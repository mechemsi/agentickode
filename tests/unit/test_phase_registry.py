# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for the phase auto-discovery registry."""

from backend.worker.phases.registry import PhaseInfo, _reset_cache, discover_phases


class TestDiscoverPhases:
    def setup_method(self):
        _reset_cache()

    def teardown_method(self):
        _reset_cache()

    def test_discover_finds_all_builtin_phases(self):
        """All built-in phase modules are discovered (ADR-009: only the modules
        the flow executor still uses remain)."""
        phases = discover_phases()
        expected = {
            "workspace_setup",
            "init",
            "finalization",
            "pr_fetch",
        }
        assert set(phases.keys()) == expected

    def test_discover_skips_internal_modules(self):
        """Modules starting with _ (helpers, prompt_resolver, etc.) are excluded."""
        phases = discover_phases()
        for name in phases:
            assert not name.startswith("_")

    def test_init_phase_name_override(self):
        """The init_phase module maps to phase name 'init'."""
        phases = discover_phases()
        assert "init" in phases
        assert "init_phase" not in phases

    def test_missing_meta_defaults(self):
        """Phases without default_agent_mode get None."""
        phases = discover_phases()

        ws = phases["workspace_setup"]
        assert ws.description == "Set up workspace on remote server"
        assert ws.default_agent_mode is None

    def test_all_phases_have_descriptions(self):
        """Every built-in phase has a non-empty description."""
        phases = discover_phases()
        for name, info in phases.items():
            assert info.description, f"Phase '{name}' has no description"

    def test_workspace_setup_and_init_are_builtin(self):
        """workspace_setup and init are the immutable prelude (ADR-007)."""
        phases = discover_phases()
        assert phases["workspace_setup"].kind == "builtin"
        assert phases["init"].kind == "builtin"
        assert phases["workspace_setup"].deprecated_in is None
        assert phases["init"].deprecated_in is None

    def test_other_phases_marked_legacy_phase_deprecated_in_0_5_0(self):
        """The remaining non-prelude phases are kind=legacy_phase, deprecated_in=0.5.0."""
        phases = discover_phases()
        for name in ("finalization", "pr_fetch"):
            info = phases[name]
            assert info.kind == "legacy_phase", f"{name} kind is {info.kind!r}"
            assert info.deprecated_in == "0.5.0", f"{name} deprecated_in is {info.deprecated_in!r}"

    def test_returns_phase_info_instances(self):
        """All values are PhaseInfo dataclass instances."""
        phases = discover_phases()
        for info in phases.values():
            assert isinstance(info, PhaseInfo)

    def test_cache_returns_same_object(self):
        """Repeated calls return the same cached dict."""
        first = discover_phases()
        second = discover_phases()
        assert first is second

    def test_reset_cache_clears(self):
        """_reset_cache() forces re-discovery on next call."""
        first = discover_phases()
        _reset_cache()
        second = discover_phases()
        assert first is not second
        assert set(first.keys()) == set(second.keys())
