# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for notification message formatter."""

from backend.services.notifications.formatter import (
    _cost_str,
    _duration_str,
    format_notification,
)


class TestHelpers:
    def test_duration_str_seconds(self):
        assert _duration_str(45) == "45s"

    def test_duration_str_minutes(self):
        assert _duration_str(185) == "3m 5s"

    def test_duration_str_hours(self):
        assert _duration_str(3661) == "1h 1m"

    def test_duration_str_none(self):
        assert _duration_str(None) == ""

    def test_cost_str_normal(self):
        assert _cost_str(1.50) == "$1.50"

    def test_cost_str_small(self):
        assert _cost_str(0.001) == "<$0.01"

    def test_cost_str_none(self):
        assert _cost_str(None) == ""


class TestFormatNotification:
    def test_run_started(self):
        msg = format_notification(
            "run_started",
            {
                "run_id": 42,
                "project_id": "my-project",
                "title": "Fix login bug",
            },
        )
        assert "Run Started" in msg
        assert "my-project #42" in msg
        assert "Fix login bug" in msg

    def test_run_completed_with_duration(self):
        msg = format_notification(
            "run_completed",
            {
                "run_id": 5,
                "project_id": "proj",
                "title": "Add tests",
                "duration": "3m 42s",
            },
        )
        assert "Run Completed" in msg
        assert "3m 42s" in msg

    def test_run_completed_without_duration(self):
        msg = format_notification(
            "run_completed",
            {
                "run_id": 5,
                "project_id": "proj",
                "title": "",
            },
        )
        assert "Run Completed" in msg
        assert "Duration" not in msg

    def test_run_failed(self):
        msg = format_notification(
            "run_failed",
            {
                "run_id": 7,
                "project_id": "api",
                "title": "Deploy",
                "error": "Test suite failed",
            },
        )
        assert "Run Failed" in msg
        assert "Test suite failed" in msg

    def test_approval_requested_with_pr(self):
        msg = format_notification(
            "approval_requested",
            {
                "run_id": 10,
                "project_id": "web",
                "title": "New feature",
                "pr_url": "https://github.com/org/repo/pull/1",
            },
        )
        assert "Approval Requested" in msg
        assert "https://github.com/org/repo/pull/1" in msg

    def test_approval_requested_without_pr(self):
        msg = format_notification(
            "approval_requested",
            {
                "run_id": 10,
                "project_id": "web",
                "title": "New feature",
            },
        )
        assert "Approval Requested" in msg
        assert "PR:" not in msg

    def test_run_started_has_deep_link(self):
        msg = format_notification(
            "run_started",
            {"run_id": 42, "project_id": "proj", "title": ""},
        )
        assert "/runs/42" in msg

    def test_run_completed_with_cost_and_duration(self):
        msg = format_notification(
            "run_completed",
            {
                "run_id": 5,
                "project_id": "proj",
                "title": "Add tests",
                "duration_seconds": 185,
                "total_cost_usd": 0.75,
            },
        )
        assert "3m 5s" in msg
        assert "$0.75" in msg

    def test_run_completed_with_pr_url(self):
        msg = format_notification(
            "run_completed",
            {
                "run_id": 5,
                "project_id": "proj",
                "title": "",
                "pr_url": "https://github.com/org/repo/pull/99",
            },
        )
        assert "https://github.com/org/repo/pull/99" in msg

    def test_plan_review_requested(self):
        msg = format_notification(
            "plan_review_requested",
            {
                "run_id": 20,
                "project_id": "api",
                "title": "Feature X",
                "subtask_count": 5,
            },
        )
        assert "Plan Review" in msg
        assert "5 subtasks" in msg
        assert "/runs/20" in msg

    def test_cost_threshold_exceeded(self):
        msg = format_notification(
            "cost_threshold_exceeded",
            {
                "run_id": 30,
                "project_id": "ml",
                "title": "Training",
                "total_cost_usd": 12.50,
                "threshold_usd": 10.00,
            },
        )
        assert "Cost Threshold" in msg
        assert "$12.50" in msg
        assert "$10.00" in msg

    def test_unknown_event(self):
        msg = format_notification(
            "custom_event",
            {
                "run_id": 1,
                "project_id": "x",
            },
        )
        assert "custom_event" in msg
        assert "/runs/1" in msg
