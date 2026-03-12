# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Role config CRUD + reset endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import RoleConfig, RolePromptOverride
from backend.repositories.role_config_repo import RoleConfigRepository
from backend.schemas import (
    RoleConfigCreate,
    RoleConfigOut,
    RoleConfigUpdate,
    RolePromptOverrideIn,
    RolePromptOverrideOut,
)
from backend.seed import AGENT_PROMPT_OVERRIDES, DEFAULT_ROLE_CONFIGS

router = APIRouter(tags=["role-configs"])

# Build lookup from seed data — single source of truth
_SYSTEM_DEFAULTS: dict[str, dict] = {
    cfg["agent_name"]: {
        "system_prompt": cfg["system_prompt"],
        "user_prompt_template": cfg["user_prompt_template"],
    }
    for cfg in DEFAULT_ROLE_CONFIGS
}


def _get_repo(db: AsyncSession = Depends(get_db)) -> RoleConfigRepository:
    return RoleConfigRepository(db)


@router.get("/role-configs", response_model=list[RoleConfigOut])
async def list_role_configs(repo: RoleConfigRepository = Depends(_get_repo)):
    return await repo.list_all()


@router.get("/role-configs/{name}", response_model=RoleConfigOut)
async def get_role_config(
    name: str,
    repo: RoleConfigRepository = Depends(_get_repo),
):
    config = await repo.get_by_name(name)
    if not config:
        raise HTTPException(404, f"Role config '{name}' not found")
    return config


@router.post("/role-configs", response_model=RoleConfigOut, status_code=201)
async def create_role_config(
    body: RoleConfigCreate,
    repo: RoleConfigRepository = Depends(_get_repo),
):
    existing = await repo.get_by_name(body.agent_name)
    if existing:
        raise HTTPException(400, f"Role '{body.agent_name}' already exists")
    config = RoleConfig(**body.model_dump(), is_system=False)
    return await repo.create(config)


@router.put("/role-configs/{name}", response_model=RoleConfigOut)
async def update_role_config(
    name: str,
    body: RoleConfigUpdate,
    repo: RoleConfigRepository = Depends(_get_repo),
):
    config = await repo.get_by_name(name)
    if not config:
        raise HTTPException(404, f"Role config '{name}' not found")
    data = body.model_dump(exclude_unset=True)
    return await repo.update(config, data)


@router.delete("/role-configs/{name}", status_code=204)
async def delete_role_config(
    name: str,
    repo: RoleConfigRepository = Depends(_get_repo),
):
    config = await repo.get_by_name(name)
    if not config:
        raise HTTPException(404, f"Role config '{name}' not found")
    if config.is_system:
        raise HTTPException(400, "Cannot delete system role")
    await repo.delete(config)


@router.post("/role-configs/{name}/reset", response_model=RoleConfigOut)
async def reset_role_config(
    name: str,
    repo: RoleConfigRepository = Depends(_get_repo),
):
    config = await repo.get_by_name(name)
    if not config:
        raise HTTPException(404, f"Role config '{name}' not found")
    if not config.is_system:
        raise HTTPException(400, "Only system roles can be reset to defaults")
    defaults = _SYSTEM_DEFAULTS.get(name)
    if not defaults:
        raise HTTPException(400, f"No defaults available for '{name}'")
    return await repo.update(config, defaults)


@router.post("/role-configs/{name}/seed-defaults")
async def seed_defaults(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """Create default RolePromptOverride rows for known CLI agents.

    Idempotent: skips agents that already have an override for this config.
    Returns a summary of created/skipped overrides.
    """
    config = await _get_config_by_name(name, db)
    created: list[str] = []
    skipped: list[str] = []

    for agent_name, defaults in AGENT_PROMPT_OVERRIDES.items():
        result = await db.execute(
            select(RolePromptOverride).where(
                RolePromptOverride.role_config_id == config.id,
                RolePromptOverride.cli_agent_name == agent_name,
            )
        )
        if result.scalar_one_or_none():
            skipped.append(agent_name)
            continue
        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name=agent_name,
            system_prompt=defaults.get("system_prompt"),
            user_prompt_template=defaults.get("user_prompt_template"),
            minimal_mode=defaults.get("minimal_mode", False),
            extra_params=defaults.get("extra_params", {}),
        )
        db.add(override)
        created.append(agent_name)

    await db.commit()
    return {"created": created, "skipped": skipped}


async def _get_config_by_name(name: str, db: AsyncSession) -> RoleConfig:
    """Fetch RoleConfig by agent_name; raise 404 if not found."""
    result = await db.execute(select(RoleConfig).where(RoleConfig.agent_name == name))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, f"Role config '{name}' not found")
    return config


@router.get("/role-configs/{name}/overrides", response_model=list[RolePromptOverrideOut])
async def list_overrides(name: str, db: AsyncSession = Depends(get_db)):
    config = await _get_config_by_name(name, db)
    result = await db.execute(
        select(RolePromptOverride).where(RolePromptOverride.role_config_id == config.id)
    )
    return result.scalars().all()


@router.put("/role-configs/{name}/overrides/{agent}", response_model=RolePromptOverrideOut)
async def upsert_override(
    name: str,
    agent: str,
    body: RolePromptOverrideIn,
    db: AsyncSession = Depends(get_db),
):
    config = await _get_config_by_name(name, db)
    result = await db.execute(
        select(RolePromptOverride).where(
            RolePromptOverride.role_config_id == config.id,
            RolePromptOverride.cli_agent_name == agent,
        )
    )
    override = result.scalar_one_or_none()
    if override:
        override.system_prompt = body.system_prompt
        override.user_prompt_template = body.user_prompt_template
        override.minimal_mode = body.minimal_mode
        override.extra_params = body.extra_params
    else:
        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name=agent,
            **body.model_dump(),
        )
        db.add(override)
    await db.commit()
    await db.refresh(override)
    return override


@router.delete("/role-configs/{name}/overrides/{agent}")
async def delete_override(
    name: str,
    agent: str,
    db: AsyncSession = Depends(get_db),
):
    config = await _get_config_by_name(name, db)
    result = await db.execute(
        select(RolePromptOverride).where(
            RolePromptOverride.role_config_id == config.id,
            RolePromptOverride.cli_agent_name == agent,
        )
    )
    override = result.scalar_one_or_none()
    if not override:
        raise HTTPException(404, f"No override for agent '{agent}'")
    await db.delete(override)
    await db.commit()
    return {"status": "deleted"}