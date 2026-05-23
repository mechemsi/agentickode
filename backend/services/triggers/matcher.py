# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""TriggerMatcher — find the WorkflowTemplate whose triggers match an event.

Used by webhook handlers (and the scheduler in a follow-up) to decide which
template to dispatch a new TaskRun under. Falls back to the default template
for plain label events when nothing else matches, preserving back-compat with
the legacy label-only routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import WorkflowTemplate

TriggerEventType = Literal["label", "issue_event", "pr_event", "schedule"]


@dataclass
class TriggerEvent:
    """Normalized external event passed to ``TriggerMatcher.match``.

    Webhook handlers translate provider-specific payloads into this shape so
    the matcher can stay payload-agnostic.
    """

    type: TriggerEventType
    source: str  # 'github' | 'gitea' | 'gitlab' | 'plane' | 'notion'
    labels: list[str] = field(default_factory=list)
    action: str | None = None  # for issue_event / pr_event
    cron_tick: str | None = None  # for schedule (the cron expression that fired)


class TriggerMatcher:
    """Resolve a ``TriggerEvent`` to a ``WorkflowTemplate``.

    Priority:
    1. Non-system templates first (user creations win over seeded ones),
       ordered by ``updated_at DESC`` so the most-recently edited template
       wins among ties.
    2. System templates second, same ordering.
    3. The default template as last-resort fallback only when the event is a
       plain label event with no labels.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def match(self, event: TriggerEvent) -> WorkflowTemplate | None:
        """Return the first WorkflowTemplate whose triggers[] match this event."""
        templates = await self._load_templates_in_priority_order()

        for tpl in templates:
            for trigger in tpl.triggers or []:
                if self._trigger_matches(trigger, event):
                    return tpl

        # Fallback: plain label event with no labels falls back to the default
        # template so that bare "open an issue with ai-task" still gets a run
        # even when the user hasn't configured any per-source label triggers.
        if event.type == "label" and not event.labels:
            return await self._get_default()

        return None

    async def _load_templates_in_priority_order(self) -> list[WorkflowTemplate]:
        # Non-system first, then system. Within each bucket, most-recently
        # updated wins.
        stmt = select(WorkflowTemplate).order_by(
            WorkflowTemplate.is_system.asc(),
            WorkflowTemplate.updated_at.desc(),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _get_default(self) -> WorkflowTemplate | None:
        stmt = select(WorkflowTemplate).where(WorkflowTemplate.is_default.is_(True))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _source_matches(trigger_source: str, event_source: str) -> bool:
        return trigger_source == "any" or trigger_source == event_source

    @classmethod
    def _trigger_matches(cls, trigger: dict, event: TriggerEvent) -> bool:
        """Evaluate a single trigger dict against a TriggerEvent."""
        ttype = trigger.get("type")

        if ttype == "manual":
            # Manual triggers never match external events.
            return False

        if ttype == "label":
            if event.type != "label":
                return False
            if not cls._source_matches(trigger.get("source", "any"), event.source):
                return False
            return cls._labels_match(trigger, event.labels)

        if ttype == "issue_event":
            if event.type != "issue_event":
                return False
            if not cls._source_matches(trigger.get("source", "any"), event.source):
                return False
            if not cls._action_matches(trigger.get("action", "any"), event.action):
                return False
            return cls._label_filter_matches(trigger.get("label_filter", []), event.labels)

        if ttype == "pr_event":
            if event.type != "pr_event":
                return False
            if not cls._source_matches(trigger.get("source", "any"), event.source):
                return False
            if not cls._action_matches(trigger.get("action", "any"), event.action):
                return False
            return cls._label_filter_matches(trigger.get("label_filter", []), event.labels)

        if ttype == "schedule":
            if event.type != "schedule":
                return False
            return trigger.get("cron") == event.cron_tick

        # Unknown trigger type -- ignore, don't false-positive.
        return False

    @staticmethod
    def _labels_match(trigger: dict, event_labels: list[str]) -> bool:
        """Apply LabelTrigger semantics: match_all ALL present AND match_any ANY present."""
        match_all = trigger.get("match_all") or []
        match_any = trigger.get("match_any") or []
        label_set = set(event_labels)

        if not match_all and not match_any:
            # Empty rule matches any label set (legacy back-compat — same as
            # the existing match_labels behavior for empty rules).
            return True

        all_ok = all(lbl in label_set for lbl in match_all) if match_all else True
        any_ok = any(lbl in label_set for lbl in match_any) if match_any else True
        return all_ok and any_ok

    @staticmethod
    def _action_matches(trigger_action: str, event_action: str | None) -> bool:
        if trigger_action == "any":
            return True
        return trigger_action == event_action

    @staticmethod
    def _label_filter_matches(label_filter: list[str], event_labels: list[str]) -> bool:
        """label_filter is AND-of-all when non-empty; empty matches anything."""
        if not label_filter:
            return True
        label_set = set(event_labels)
        return all(lbl in label_set for lbl in label_filter)
