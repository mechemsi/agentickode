# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Prompt resolution helper: applies per-agent overrides to base RoleConfig prompts."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import RoleConfig, RolePromptOverride

logger = logging.getLogger("agentickode.prompt_resolver")


async def build_project_instructions_section(
    session: AsyncSession,
    project_id: str,
    phase_name: str,
) -> tuple[str, list[str]]:
    """Build the project instructions section for prepending to system prompt.

    Returns (markdown_section, list_of_secret_names_injected).
    """
    from backend.repositories.project_instruction_repo import ProjectInstructionRepository
    from backend.repositories.project_secret_repo import ProjectSecretRepository

    instr_repo = ProjectInstructionRepository(session)
    secret_repo = ProjectSecretRepository(session)

    parts: list[str] = []

    global_instr = await instr_repo.get_global(project_id)
    if global_instr and global_instr.is_active and global_instr.content.strip():
        parts.append("## Project Instructions\n" + global_instr.content.strip())

    phase_instr = await instr_repo.get_for_phase(project_id, phase_name)
    if phase_instr and phase_instr.is_active and phase_instr.content.strip():
        parts.append(
            f"## Phase-Specific Instructions ({phase_name})\n" + phase_instr.content.strip()
        )

    _, prompt_secrets = await secret_repo.get_decrypted_for_phase(project_id, phase_name)
    secret_names: list[str] = []
    if prompt_secrets:
        cred_lines = [f"- {name}: {value}" for name, value in prompt_secrets]
        parts.append("## Available Credentials\n" + "\n".join(cred_lines))
        secret_names = [name for name, _ in prompt_secrets]

    section = "\n\n".join(parts)
    return section, secret_names


async def resolve_prompts(
    config: RoleConfig | None,
    adapter: object,
    session: AsyncSession,
    fallback_system: str,
    fallback_template: str,
    project_id: str | None = None,
    phase_name: str | None = None,
) -> tuple[str, str, dict, dict[str, str]]:
    """Resolve system_prompt, user_template, extra_params, and project env vars.

    Resolution order:
    1. Start with RoleConfig values (or fallbacks if config is None / fields empty).
    2. If the adapter is a CLIAdapter (has agent_name), check for a RolePromptOverride.
    3. If minimal_mode is set on the override: clear system_prompt entirely and use
       the override's user_prompt_template (if set) or keep the current template.
    4. Otherwise apply any non-None fields from the override.
    5. Merge extra_params from config and override (override wins on key conflicts).
    6. If project_id is set, prepend project instructions and collect env var secrets.
    """
    system_prompt: str = (
        str(config.system_prompt) if config and config.system_prompt else fallback_system
    )
    user_template: str = (
        str(config.user_prompt_template)
        if config and config.user_prompt_template
        else fallback_template
    )
    extra: dict[str, object] = {**config.extra_params} if config and config.extra_params else {}

    cli_agent_name: str | None = getattr(adapter, "agent_name", None)
    if cli_agent_name and config:
        result = await session.execute(
            select(RolePromptOverride).where(
                RolePromptOverride.role_config_id == config.id,
                RolePromptOverride.cli_agent_name == cli_agent_name,
            )
        )
        override = result.scalar_one_or_none()
        if override:
            if override.extra_params:
                extra = {**extra, **override.extra_params}
            if override.minimal_mode:
                system_prompt = ""
                if override.user_prompt_template is not None:
                    user_template = str(override.user_prompt_template)
            else:
                if override.system_prompt is not None:
                    system_prompt = str(override.system_prompt)
                if override.user_prompt_template is not None:
                    user_template = str(override.user_prompt_template)

    project_env_vars: dict[str, str] = {}
    if project_id and phase_name:
        try:
            section, secret_names = await build_project_instructions_section(
                session, project_id, phase_name
            )
            if section:
                system_prompt = section + "\n\n" + system_prompt
                logger.info(
                    "Injected project instructions for %s/%s (secrets: %s)",
                    project_id,
                    phase_name,
                    [f"{n}=***" for n in secret_names],
                )

            from backend.repositories.project_secret_repo import ProjectSecretRepository

            secret_repo = ProjectSecretRepository(session)
            project_env_vars, _ = await secret_repo.get_decrypted_for_phase(project_id, phase_name)
        except Exception:
            logger.exception("Failed to load project instructions for %s", project_id)

    return system_prompt, user_template, extra, project_env_vars
