# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Prompt resolution: phase fallback prompts + per-agent minimal_mode + project instructions."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentSettings

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
    agent_settings: AgentSettings | None,
    adapter: object,
    session: AsyncSession,
    fallback_system: str,
    fallback_template: str,
    project_id: str | None = None,
    phase_name: str | None = None,
) -> tuple[str, str, dict, dict[str, str]]:
    """Resolve system_prompt, user_template, extra_params, and project env vars.

    Resolution order:
    1. Start from the phase's fallback system/user prompts.
    2. If the resolved agent has ``minimal_mode`` (e.g. claude, which supplies its own
       system prompt), clear the system prompt.
    3. If project_id is set, prepend project instructions and collect env var secrets.
    """
    system_prompt: str = fallback_system
    user_template: str = fallback_template
    extra: dict[str, object] = {}

    if agent_settings is not None and getattr(agent_settings, "minimal_mode", False):
        system_prompt = ""

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
