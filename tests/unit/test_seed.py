# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for seed data — ensures fresh installs get all required fixtures."""

import pytest
from sqlalchemy import select

from backend.models import AgentSettings, RoleConfig, WorkflowTemplate
from backend.models.agents import RolePromptOverride
from backend.seed import (
    AGENT_PROMPT_OVERRIDES,
    DEFAULT_AGENT_SETTINGS,
    DEFAULT_ROLE_CONFIGS,
    DEFAULT_WORKFLOW_TEMPLATES,
    seed_all,
)


@pytest.fixture
async def seeded_db(db_session):
    """Run seed_all on a fresh database and return the session."""
    await seed_all(db_session)
    return db_session


class TestSeedAll:
    """Verify seed_all populates all required data."""

    async def test_seeds_agent_settings(self, seeded_db):
        result = await seeded_db.execute(select(AgentSettings))
        settings = result.scalars().all()
        names = {s.agent_name for s in settings}
        expected = {d["agent_name"] for d in DEFAULT_AGENT_SETTINGS}
        assert names == expected

    async def test_agent_settings_have_command_templates(self, seeded_db):
        result = await seeded_db.execute(select(AgentSettings))
        for s in result.scalars().all():
            # openhands has empty command_templates, skip it
            if s.agent_name == "openhands":
                continue
            assert s.command_templates, f"{s.agent_name} missing command_templates"

    async def test_agent_settings_have_install_metadata(self, seeded_db):
        """All seeded agents should have install metadata populated."""
        result = await seeded_db.execute(select(AgentSettings))
        for s in result.scalars().all():
            assert s.agent_type in (
                "cli_binary",
                "api_service",
            ), f"{s.agent_name} missing agent_type"
            assert s.check_cmd, f"{s.agent_name} missing check_cmd"
            assert s.install_cmd, f"{s.agent_name} missing install_cmd"

    async def test_cli_agents_need_non_root(self, seeded_db):
        """All CLI binary agents should have needs_non_root=True."""
        result = await seeded_db.execute(
            select(AgentSettings).where(AgentSettings.agent_type == "cli_binary")
        )
        for s in result.scalars().all():
            assert s.needs_non_root is True, f"{s.agent_name} should need non-root"

    async def test_api_service_agents_not_non_root(self, seeded_db):
        """API service agents (openhands) should have needs_non_root=False."""
        result = await seeded_db.execute(
            select(AgentSettings).where(AgentSettings.agent_type == "api_service")
        )
        for s in result.scalars().all():
            assert s.needs_non_root is False, f"{s.agent_name} should not need non-root"

    async def test_openhands_is_api_service(self, seeded_db):
        """OpenHands should be agent_type='api_service'."""
        result = await seeded_db.execute(
            select(AgentSettings).where(AgentSettings.agent_name == "openhands")
        )
        openhands = result.scalar_one()
        assert openhands.agent_type == "api_service"

    async def test_seeds_all_workflow_templates(self, seeded_db):
        result = await seeded_db.execute(select(WorkflowTemplate))
        templates = result.scalars().all()
        names = {t.name for t in templates}
        expected = {d["name"] for d in DEFAULT_WORKFLOW_TEMPLATES}
        assert names == expected

    async def test_exactly_one_default_workflow(self, seeded_db):
        result = await seeded_db.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.is_default.is_(True))
        )
        defaults = result.scalars().all()
        assert len(defaults) == 1
        assert defaults[0].name == "default"

    async def test_all_workflow_templates_are_system(self, seeded_db):
        result = await seeded_db.execute(select(WorkflowTemplate))
        for t in result.scalars().all():
            assert t.is_system is True, f"{t.name} should be is_system=True"

    async def test_workflow_templates_have_phases(self, seeded_db):
        result = await seeded_db.execute(select(WorkflowTemplate))
        for t in result.scalars().all():
            assert t.phases, f"{t.name} has no phases"

    async def test_seeds_role_configs(self, seeded_db):
        result = await seeded_db.execute(select(RoleConfig).where(RoleConfig.is_system.is_(True)))
        configs = result.scalars().all()
        names = {c.agent_name for c in configs}
        expected = {d["agent_name"] for d in DEFAULT_ROLE_CONFIGS}
        assert names == expected

    async def test_role_configs_have_prompts(self, seeded_db):
        result = await seeded_db.execute(select(RoleConfig).where(RoleConfig.is_system.is_(True)))
        for c in result.scalars().all():
            assert c.system_prompt, f"{c.agent_name} missing system_prompt"
            assert c.user_prompt_template, f"{c.agent_name} missing user_prompt_template"

    async def test_seeds_prompt_overrides(self, seeded_db):
        result = await seeded_db.execute(select(RolePromptOverride))
        overrides = result.scalars().all()
        # 3 system configs x N CLI agents
        expected_count = len(DEFAULT_ROLE_CONFIGS) * len(AGENT_PROMPT_OVERRIDES)
        assert len(overrides) == expected_count

    async def test_claude_override_is_minimal(self, seeded_db):
        result = await seeded_db.execute(
            select(RolePromptOverride).where(RolePromptOverride.cli_agent_name == "claude")
        )
        overrides = result.scalars().all()
        assert len(overrides) == len(DEFAULT_ROLE_CONFIGS)
        for o in overrides:
            assert o.minimal_mode is True


class TestSeedIdempotent:
    """Verify seed_all is safe to call multiple times."""

    async def test_double_seed_no_duplicates(self, db_session):
        await seed_all(db_session)
        await seed_all(db_session)

        settings = (await db_session.execute(select(AgentSettings))).scalars().all()
        assert len(settings) == len(DEFAULT_AGENT_SETTINGS)

        templates = (await db_session.execute(select(WorkflowTemplate))).scalars().all()
        assert len(templates) == len(DEFAULT_WORKFLOW_TEMPLATES)

        configs = (
            (await db_session.execute(select(RoleConfig).where(RoleConfig.is_system.is_(True))))
            .scalars()
            .all()
        )
        assert len(configs) == len(DEFAULT_ROLE_CONFIGS)

    async def test_backfills_command_templates(self, db_session):
        """Existing agent settings with empty templates get backfilled."""
        db_session.add(
            AgentSettings(
                agent_name="claude",
                display_name="Claude CLI",
                description="test",
                command_templates={},
            )
        )
        await db_session.commit()

        await seed_all(db_session)

        result = await db_session.execute(
            select(AgentSettings).where(AgentSettings.agent_name == "claude")
        )
        setting = result.scalar_one()
        assert setting.command_templates  # Should be backfilled

    async def test_backfills_install_metadata(self, db_session):
        """Existing agent settings without install metadata get backfilled."""
        db_session.add(
            AgentSettings(
                agent_name="claude",
                display_name="Claude CLI",
                description="test",
                command_templates={"generate": "cat {prompt_file} | claude --print"},
                # No install metadata — simulates pre-015 row
            )
        )
        await db_session.commit()

        await seed_all(db_session)

        result = await db_session.execute(
            select(AgentSettings).where(AgentSettings.agent_name == "claude")
        )
        setting = result.scalar_one()
        assert setting.check_cmd == "command -v claude"
        assert setting.install_cmd is not None
        assert setting.needs_non_root is True
        assert setting.agent_type == "cli_binary"
