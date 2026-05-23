# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Integration tests for the workflow-templates API."""

import pytest

from backend.models import WorkflowTemplate


@pytest.fixture()
async def label_template(db_session):
    tpl = WorkflowTemplate(
        name="dry-run-fixture",
        description="",
        label_rules=[],
        triggers=[
            {"type": "label", "source": "github", "match_any": ["ai-task"]},
            {"type": "issue_event", "source": "any", "action": "opened"},
        ],
        phases=[{"phase_name": "init", "enabled": True}],
        is_default=False,
        is_system=False,
    )
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)
    return tpl


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


class TestDryRunEndpoint:
    async def test_matched_label_trigger_returns_template_and_reason(self, client, label_template):
        resp = await client.post(
            f"/api/workflow-templates/{label_template.id}/dry-run",
            json={"type": "label", "source": "github", "labels": ["ai-task"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["matched"] is True
        assert body["template"]["id"] == label_template.id
        assert "matched trigger #0" in body["reason"]
        assert "label" in body["reason"]

    async def test_matched_issue_event_returns_second_trigger_index(self, client, label_template):
        resp = await client.post(
            f"/api/workflow-templates/{label_template.id}/dry-run",
            json={"type": "issue_event", "source": "gitea", "action": "opened"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["matched"] is True
        assert "matched trigger #1" in body["reason"]
        assert "issue_event" in body["reason"]

    async def test_no_match_returns_none_template(self, client, label_template):
        resp = await client.post(
            f"/api/workflow-templates/{label_template.id}/dry-run",
            json={"type": "label", "source": "gitea", "labels": ["bug"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["matched"] is False
        assert body["template"] is None
        assert body["reason"] == "no triggers matched"

    async def test_unknown_template_returns_404(self, client):
        resp = await client.post(
            "/api/workflow-templates/99999/dry-run",
            json={"type": "label", "source": "github", "labels": ["ai-task"]},
        )
        assert resp.status_code == 404

    async def test_invalid_event_type_returns_422(self, client, label_template):
        resp = await client.post(
            f"/api/workflow-templates/{label_template.id}/dry-run",
            json={"type": "not-an-event", "source": "github"},
        )
        assert resp.status_code == 422
