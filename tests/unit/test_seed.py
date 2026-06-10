# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for seed data — ensures fresh installs get all required fixtures."""

import pytest
from sqlalchemy import select

from backend.models import AgentSettings, FlowPrompt
from backend.seed import (
    DEFAULT_AGENT_SETTINGS,
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

    async def test_seeds_flow_prompts(self, seeded_db):
        """ADR-009: seed_all installs the implement + pr_review flow prompts."""
        result = await seeded_db.execute(select(FlowPrompt))
        flow_types = {f.flow_type for f in result.scalars().all()}
        assert {"implement", "pr_review"} <= flow_types

    async def test_flow_prompts_are_system(self, seeded_db):
        result = await seeded_db.execute(select(FlowPrompt))
        for f in result.scalars().all():
            assert f.is_system is True, f"{f.name} should be is_system=True"


class TestSeedIdempotent:
    """Verify seed_all is safe to call multiple times."""

    async def test_double_seed_no_duplicates(self, db_session):
        await seed_all(db_session)
        await seed_all(db_session)

        settings = (await db_session.execute(select(AgentSettings))).scalars().all()
        assert len(settings) == len(DEFAULT_AGENT_SETTINGS)

        flows = (await db_session.execute(select(FlowPrompt))).scalars().all()
        # No duplicates on second seed — count stays equal to distinct names.
        assert len(flows) == len({f.name for f in flows})

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
