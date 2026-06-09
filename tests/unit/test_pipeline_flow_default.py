# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for the Phase 3 implement-flow default guard (ADR-009)."""

from types import SimpleNamespace

from backend.worker.pipeline import _defaults_to_implement_flow


class TestDefaultsToImplementFlow:
    def test_normal_run_defaults_to_implement(self):
        run = SimpleNamespace(task_source_meta={})
        assert _defaults_to_implement_flow(run) is True

    def test_none_meta_defaults_to_implement(self):
        run = SimpleNamespace(task_source_meta=None)
        assert _defaults_to_implement_flow(run) is True

    def test_pr_review_run_not_defaulted(self):
        # A PR-review run must never become an implement (code-writing) job.
        run = SimpleNamespace(task_source_meta={"review_mode": "comment", "pr_number": 31})
        assert _defaults_to_implement_flow(run) is False
