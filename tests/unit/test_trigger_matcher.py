# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.triggers.matcher.TriggerMatcher."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.models import WorkflowTemplate
from backend.services.triggers import TriggerEvent, TriggerMatcher


async def _add_template(
    db_session,
    *,
    name: str,
    triggers: list[dict],
    is_default: bool = False,
    is_system: bool = False,
    updated_at: datetime | None = None,
) -> WorkflowTemplate:
    tpl = WorkflowTemplate(
        name=name,
        description=f"test template {name}",
        label_rules=[],
        triggers=triggers,
        phases=[{"phase_name": "init", "enabled": True}],
        is_default=is_default,
        is_system=is_system,
    )
    db_session.add(tpl)
    await db_session.commit()
    await db_session.refresh(tpl)
    if updated_at is not None:
        tpl.updated_at = updated_at
        await db_session.commit()
        await db_session.refresh(tpl)
    return tpl


class TestLabelTriggerMatching:
    async def test_matches_label_when_match_any_present(self, db_session):
        await _add_template(
            db_session,
            name="ai-task",
            triggers=[
                {"type": "label", "source": "any", "match_all": [], "match_any": ["ai-task"]}
            ],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="github", labels=["ai-task"]))
        assert tpl is not None
        assert tpl.name == "ai-task"

    async def test_does_not_match_when_label_missing(self, db_session):
        await _add_template(
            db_session,
            name="ai-task",
            triggers=[{"type": "label", "match_any": ["ai-task"]}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="github", labels=["bug"]))
        assert tpl is None

    async def test_source_filter_excludes_other_sources(self, db_session):
        await _add_template(
            db_session,
            name="github-only",
            triggers=[{"type": "label", "source": "github", "match_any": ["ai-task"]}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="gitea", labels=["ai-task"]))
        assert tpl is None

    async def test_source_any_matches_all_sources(self, db_session):
        await _add_template(
            db_session,
            name="any-source",
            triggers=[{"type": "label", "source": "any", "match_any": ["ai-task"]}],
        )
        matcher = TriggerMatcher(db_session)
        for src in ("github", "gitea", "gitlab", "plane", "notion"):
            tpl = await matcher.match(TriggerEvent(type="label", source=src, labels=["ai-task"]))
            assert tpl is not None, f"expected match for source={src}"
            assert tpl.name == "any-source"

    async def test_match_all_requires_every_label(self, db_session):
        await _add_template(
            db_session,
            name="strict",
            triggers=[{"type": "label", "match_all": ["a", "b"]}],
        )
        matcher = TriggerMatcher(db_session)
        assert (
            await matcher.match(TriggerEvent(type="label", source="github", labels=["a"])) is None
        )
        tpl = await matcher.match(
            TriggerEvent(type="label", source="github", labels=["a", "b", "c"])
        )
        assert tpl is not None and tpl.name == "strict"


class TestIssueEventTriggerMatching:
    async def test_matches_action_opened(self, db_session):
        await _add_template(
            db_session,
            name="issue-opened",
            triggers=[{"type": "issue_event", "source": "github", "action": "opened"}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(
            TriggerEvent(type="issue_event", source="github", action="opened")
        )
        assert tpl is not None and tpl.name == "issue-opened"

    async def test_does_not_match_different_action(self, db_session):
        await _add_template(
            db_session,
            name="issue-opened",
            triggers=[{"type": "issue_event", "action": "opened"}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(
            TriggerEvent(type="issue_event", source="github", action="labeled")
        )
        assert tpl is None

    async def test_action_any_matches_anything(self, db_session):
        await _add_template(
            db_session,
            name="any-action",
            triggers=[{"type": "issue_event", "action": "any"}],
        )
        matcher = TriggerMatcher(db_session)
        for action in ("opened", "labeled", "commented"):
            tpl = await matcher.match(
                TriggerEvent(type="issue_event", source="github", action=action)
            )
            assert tpl is not None and tpl.name == "any-action"

    async def test_label_filter_must_all_be_present(self, db_session):
        await _add_template(
            db_session,
            name="filtered",
            triggers=[{"type": "issue_event", "action": "any", "label_filter": ["ai-task"]}],
        )
        matcher = TriggerMatcher(db_session)
        no_label = await matcher.match(
            TriggerEvent(type="issue_event", source="github", action="opened", labels=[])
        )
        assert no_label is None
        with_label = await matcher.match(
            TriggerEvent(type="issue_event", source="github", action="opened", labels=["ai-task"])
        )
        assert with_label is not None and with_label.name == "filtered"

    async def test_does_not_false_positive_on_label_event(self, db_session):
        await _add_template(
            db_session,
            name="issue-only",
            triggers=[{"type": "issue_event", "action": "any"}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="notion", labels=["ai-task"]))
        assert tpl is None


class TestPrEventTriggerMatching:
    async def test_matches_review_requested(self, db_session):
        await _add_template(
            db_session,
            name="pr-review",
            triggers=[{"type": "pr_event", "source": "github", "action": "review_requested"}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(
            TriggerEvent(type="pr_event", source="github", action="review_requested")
        )
        assert tpl is not None and tpl.name == "pr-review"

    async def test_does_not_match_issue_event(self, db_session):
        await _add_template(
            db_session,
            name="pr-only",
            triggers=[{"type": "pr_event", "action": "any"}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(
            TriggerEvent(type="issue_event", source="github", action="opened")
        )
        assert tpl is None


class TestScheduleTriggerMatching:
    async def test_matches_exact_cron_tick(self, db_session):
        await _add_template(
            db_session,
            name="cron-hourly",
            triggers=[{"type": "schedule", "cron": "0 * * * *"}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(
            TriggerEvent(type="schedule", source="cron", cron_tick="0 * * * *")
        )
        assert tpl is not None and tpl.name == "cron-hourly"

    async def test_does_not_match_different_cron(self, db_session):
        await _add_template(
            db_session,
            name="cron-hourly",
            triggers=[{"type": "schedule", "cron": "0 * * * *"}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(
            TriggerEvent(type="schedule", source="cron", cron_tick="*/5 * * * *")
        )
        assert tpl is None


class TestManualTrigger:
    async def test_manual_trigger_never_matches_external_event(self, db_session):
        await _add_template(
            db_session,
            name="manual-only",
            triggers=[{"type": "manual"}],
        )
        matcher = TriggerMatcher(db_session)
        # Try every event type — none should match.
        candidates = [
            TriggerEvent(type="label", source="github", labels=["ai-task"]),
            TriggerEvent(type="issue_event", source="github", action="opened"),
            TriggerEvent(type="pr_event", source="github", action="opened"),
            TriggerEvent(type="schedule", source="cron", cron_tick="* * * * *"),
        ]
        for ev in candidates:
            assert await matcher.match(ev) is None


class TestPriorityOrdering:
    async def test_user_template_beats_system_template(self, db_session):
        await _add_template(
            db_session,
            name="system-tpl",
            triggers=[{"type": "label", "match_any": ["ai-task"]}],
            is_system=True,
        )
        await _add_template(
            db_session,
            name="user-tpl",
            triggers=[{"type": "label", "match_any": ["ai-task"]}],
            is_system=False,
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="github", labels=["ai-task"]))
        assert tpl is not None and tpl.name == "user-tpl"

    async def test_most_recently_updated_wins_within_bucket(self, db_session):
        older = datetime.now(UTC) - timedelta(hours=1)
        newer = datetime.now(UTC)
        await _add_template(
            db_session,
            name="older",
            triggers=[{"type": "label", "match_any": ["ai-task"]}],
            updated_at=older,
        )
        await _add_template(
            db_session,
            name="newer",
            triggers=[{"type": "label", "match_any": ["ai-task"]}],
            updated_at=newer,
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="github", labels=["ai-task"]))
        assert tpl is not None and tpl.name == "newer"


class TestDefaultFallback:
    async def test_label_event_with_no_labels_falls_back_to_default(self, db_session):
        default_tpl = await _add_template(
            db_session,
            name="default",
            triggers=[],
            is_default=True,
            is_system=True,
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="github", labels=[]))
        assert tpl is not None and tpl.id == default_tpl.id

    async def test_no_match_returns_none_when_labels_present(self, db_session):
        await _add_template(
            db_session,
            name="default",
            triggers=[],
            is_default=True,
            is_system=True,
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="github", labels=["random"]))
        assert tpl is None

    async def test_no_match_returns_none_for_non_label_event(self, db_session):
        await _add_template(
            db_session,
            name="default",
            triggers=[],
            is_default=True,
            is_system=True,
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(
            TriggerEvent(type="issue_event", source="github", action="opened")
        )
        assert tpl is None


class TestUnknownTriggerType:
    async def test_unknown_type_is_ignored(self, db_session):
        await _add_template(
            db_session,
            name="weird",
            triggers=[{"type": "future_type"}],
        )
        matcher = TriggerMatcher(db_session)
        tpl = await matcher.match(TriggerEvent(type="label", source="github", labels=["ai-task"]))
        assert tpl is None


@pytest.mark.parametrize("event_type", ["label", "issue_event", "pr_event", "schedule"])
async def test_empty_triggers_never_match(db_session, event_type):
    await _add_template(db_session, name="empty", triggers=[])
    matcher = TriggerMatcher(db_session)
    ev = TriggerEvent(
        type=event_type,  # type: ignore[arg-type]
        source="github",
        labels=["ai-task"],
        action="opened",
        cron_tick="* * * * *",
    )
    tpl = await matcher.match(ev)
    # Empty triggers shouldn't match; only the default-fallback path matters,
    # and we have no default here.
    assert tpl is None
