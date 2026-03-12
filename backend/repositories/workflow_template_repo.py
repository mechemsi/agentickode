# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Repository for WorkflowTemplate database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import WorkflowTemplate


class WorkflowTemplateRepository:
    """Encapsulates all WorkflowTemplate database queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[WorkflowTemplate]:
        result = await self._session.execute(
            select(WorkflowTemplate).order_by(WorkflowTemplate.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, template_id: int) -> WorkflowTemplate | None:
        return await self._session.get(WorkflowTemplate, template_id)

    async def get_by_name(self, name: str) -> WorkflowTemplate | None:
        result = await self._session.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == name)
        )
        return result.scalar_one_or_none()

    async def get_default(self) -> WorkflowTemplate | None:
        result = await self._session.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.is_default.is_(True))
        )
        return result.scalar_one_or_none()

    async def create(self, template: WorkflowTemplate) -> WorkflowTemplate:
        self._session.add(template)
        await self._session.commit()
        await self._session.refresh(template)
        return template

    async def update(self, template: WorkflowTemplate, data: dict) -> WorkflowTemplate:
        for field, value in data.items():
            setattr(template, field, value)
        await self._session.commit()
        await self._session.refresh(template)
        return template

    async def delete(self, template: WorkflowTemplate) -> None:
        await self._session.delete(template)
        await self._session.commit()

    async def match_labels(self, labels: list[str]) -> WorkflowTemplate | None:
        """Find the first non-default template whose label_rules match the given labels."""
        result = await self._session.execute(
            select(WorkflowTemplate)
            .where(WorkflowTemplate.is_default.is_(False))
            .order_by(WorkflowTemplate.name)
        )
        templates = result.scalars().all()
        label_set = set(labels)

        for template in templates:
            rules = template.label_rules or []
            if not rules:
                continue
            if self._rules_match(rules, label_set):
                return template

        return await self.get_default()

    @staticmethod
    def _rules_match(rules: list[dict], label_set: set[str]) -> bool:
        """Evaluate label rules: at least one rule must match."""
        for rule in rules:
            match_all = rule.get("match_all", [])
            match_any = rule.get("match_any", [])

            all_ok = all(lbl in label_set for lbl in match_all) if match_all else True
            any_ok = any(lbl in label_set for lbl in match_any) if match_any else True

            if all_ok and any_ok:
                return True
        return False