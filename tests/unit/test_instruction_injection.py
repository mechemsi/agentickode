# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for project instruction injection into resolve_prompts."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ProjectConfig
from backend.models.instructions import ProjectInstruction, ProjectSecret
from backend.services.encryption import encrypt_value
from backend.worker.phases._prompt_resolver import (
    build_project_instructions_section,
    resolve_prompts,
)


@pytest.fixture()
async def project(db_session):
    p = ProjectConfig(
        project_id="inj-proj",
        project_slug="injection-test",
        repo_owner="org",
        repo_name="repo",
        default_branch="main",
        task_source="plane",
        git_provider="gitea",
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture(autouse=True)
def _patch_encryption():
    """Patch encryption to use a stable test key."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    import backend.services.encryption as enc_mod

    enc_mod._fernet = None
    with patch.object(enc_mod, "settings") as mock_settings:
        mock_settings.encryption_key = key
        yield
    enc_mod._fernet = None


@pytest.mark.asyncio
async def test_resolve_prompts_without_project_id(db_session: AsyncSession):
    """Backward compat: no project_id returns empty env vars."""
    system, template, extra, env_vars = await resolve_prompts(
        None, object(), db_session, "fallback system", "fallback template"
    )
    assert system == "fallback system"
    assert template == "fallback template"
    assert env_vars == {}


@pytest.mark.asyncio
async def test_resolve_prompts_with_global_instruction(db_session: AsyncSession, project):
    """Global instruction is prepended to system prompt."""
    db_session.add(
        ProjectInstruction(
            project_id="inj-proj",
            phase_name="__global__",
            content="Always use TDD",
            is_active=True,
        )
    )
    await db_session.commit()

    system, _, _, _ = await resolve_prompts(
        None,
        object(),
        db_session,
        "base system",
        "template",
        project_id="inj-proj",
        phase_name="coding",
    )
    assert "Always use TDD" in system
    assert "base system" in system


@pytest.mark.asyncio
async def test_resolve_prompts_with_phase_instruction(db_session: AsyncSession, project):
    """Phase-specific instruction appears in system prompt."""
    db_session.add(
        ProjectInstruction(
            project_id="inj-proj",
            phase_name="coding",
            content="Run pytest after changes",
            is_active=True,
        )
    )
    await db_session.commit()

    system, _, _, _ = await resolve_prompts(
        None,
        object(),
        db_session,
        "base",
        "tpl",
        project_id="inj-proj",
        phase_name="coding",
    )
    assert "Run pytest after changes" in system
    assert "Phase-Specific Instructions (coding)" in system


@pytest.mark.asyncio
async def test_global_plus_phase_merged(db_session: AsyncSession, project):
    """Both global and phase instructions appear."""
    db_session.add(
        ProjectInstruction(
            project_id="inj-proj",
            phase_name="__global__",
            content="Global rules",
            is_active=True,
        )
    )
    db_session.add(
        ProjectInstruction(
            project_id="inj-proj",
            phase_name="planning",
            content="Planning rules",
            is_active=True,
        )
    )
    await db_session.commit()

    system, _, _, _ = await resolve_prompts(
        None,
        object(),
        db_session,
        "base",
        "tpl",
        project_id="inj-proj",
        phase_name="planning",
    )
    assert "Global rules" in system
    assert "Planning rules" in system


@pytest.mark.asyncio
async def test_prompt_secret_injection(db_session: AsyncSession, project):
    """Secrets with inject_as=prompt appear in system prompt section."""
    db_session.add(
        ProjectSecret(
            project_id="inj-proj",
            name="DB_PASS",
            encrypted_value=encrypt_value("mypassword"),
            inject_as="prompt",
            phase_scope=None,
        )
    )
    await db_session.commit()

    section, secret_names = await build_project_instructions_section(
        db_session, "inj-proj", "coding"
    )
    assert "DB_PASS" in section
    assert "mypassword" in section
    assert "DB_PASS" in secret_names


@pytest.mark.asyncio
async def test_env_var_secret_returned(db_session: AsyncSession, project):
    """Secrets with inject_as=env_var returned as env dict."""
    db_session.add(
        ProjectSecret(
            project_id="inj-proj",
            name="API_KEY",
            encrypted_value=encrypt_value("key123"),
            inject_as="env_var",
            phase_scope=None,
        )
    )
    await db_session.commit()

    _, _, _, env_vars = await resolve_prompts(
        None,
        object(),
        db_session,
        "base",
        "tpl",
        project_id="inj-proj",
        phase_name="coding",
    )
    assert env_vars["API_KEY"] == "key123"


@pytest.mark.asyncio
async def test_phase_scope_filtering(db_session: AsyncSession, project):
    """Secrets with phase_scope are only returned for matching phases."""
    db_session.add(
        ProjectSecret(
            project_id="inj-proj",
            name="CODING_ONLY",
            encrypted_value=encrypt_value("val"),
            inject_as="env_var",
            phase_scope="coding",
        )
    )
    await db_session.commit()

    # Should be included for coding
    _, _, _, env_coding = await resolve_prompts(
        None,
        object(),
        db_session,
        "base",
        "tpl",
        project_id="inj-proj",
        phase_name="coding",
    )
    assert "CODING_ONLY" in env_coding

    # Should NOT be included for planning
    _, _, _, env_planning = await resolve_prompts(
        None,
        object(),
        db_session,
        "base",
        "tpl",
        project_id="inj-proj",
        phase_name="planning",
    )
    assert "CODING_ONLY" not in env_planning


@pytest.mark.asyncio
async def test_inactive_instruction_ignored(db_session: AsyncSession, project):
    """Inactive instructions are not included."""
    db_session.add(
        ProjectInstruction(
            project_id="inj-proj",
            phase_name="__global__",
            content="Should not appear",
            is_active=False,
        )
    )
    await db_session.commit()

    system, _, _, _ = await resolve_prompts(
        None,
        object(),
        db_session,
        "base",
        "tpl",
        project_id="inj-proj",
        phase_name="coding",
    )
    assert "Should not appear" not in system
