# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for the workflow-templates API."""


class TestStepKindsEndpoint:
    async def test_returns_bash_agent_and_legacy_phase_entries(self, client):
        resp = await client.get("/api/step-kinds")
        assert resp.status_code == 200
        data = resp.json()
        kinds = {entry["kind"] for entry in data}
        assert kinds == {"bash", "agent", "legacy_phase"}

    async def test_bash_kind_has_command_in_params_schema(self, client):
        resp = await client.get("/api/step-kinds")
        bash = next(e for e in resp.json() if e["kind"] == "bash")
        assert "command" in bash["params_schema"]
        assert bash["params_schema"]["command"]["required"] is True
        # Templating hint is mentioned so UI authors know about it
        assert "{{steps." in bash["params_schema"]["command"]["description"]

    async def test_agent_kind_has_prompt_and_mode(self, client):
        resp = await client.get("/api/step-kinds")
        agent = next(e for e in resp.json() if e["kind"] == "agent")
        assert agent["params_schema"]["prompt"]["required"] is True
        mode = agent["params_schema"]["mode"]
        assert mode["enum"] == ["generate", "task"]
        assert mode["default"] == "generate"

    async def test_legacy_phase_kind_enumerates_discovered_phases(self, client):
        """`values` is the discovered phase-module list so the UI can dropdown them."""
        resp = await client.get("/api/step-kinds")
        legacy = next(e for e in resp.json() if e["kind"] == "legacy_phase")
        assert isinstance(legacy["values"], list)
        # At minimum the foundational phases must be discoverable
        for required in ("workspace_setup", "init", "coding"):
            assert (
                required in legacy["values"]
            ), f"{required} should be in legacy phase list; got {legacy['values']}"
