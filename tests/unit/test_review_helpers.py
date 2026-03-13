# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for review helper functions."""

from backend.worker.phases._review_helpers import (
    build_fix_instruction,
    build_review_prompt,
    parse_review_response,
    record_iteration,
    should_retry,
)


class TestParseReviewResponse:
    def test_approved(self):
        resp = '{"approved": true, "issues": [], "suggestions": ["Nice work"]}'
        parsed = parse_review_response(resp)
        assert parsed["approved"] is True
        assert parsed["issues"] == []
        assert parsed["critical"] == []

    def test_critical_overrides_approval(self):
        resp = (
            '{"approved": true, "issues": '
            '[{"severity": "critical", "description": "SQL injection"}], '
            '"suggestions": []}'
        )
        parsed = parse_review_response(resp)
        assert parsed["approved"] is False
        assert len(parsed["critical"]) == 1

    def test_invalid_json(self):
        parsed = parse_review_response("This is not JSON at all")
        assert parsed["approved"] is False
        assert len(parsed["issues"]) == 1
        assert "Failed to parse" in parsed["issues"][0]["description"]


class TestShouldRetry:
    def _parsed(self, approved=False, critical_count=0):
        critical = [
            {"severity": "critical", "description": f"issue {i}"} for i in range(critical_count)
        ]
        issues = [*critical, {"severity": "minor", "description": "minor"}]
        return {"approved": approved, "issues": issues, "critical": critical}

    def test_approved_no_retry(self):
        assert should_retry(self._parsed(approved=True), "strict", 0, 3) is False

    def test_max_retries_exhausted(self):
        assert should_retry(self._parsed(critical_count=1), "strict", 3, 3) is False

    def test_strict_retries_on_any_non_approved(self):
        parsed = self._parsed(approved=False, critical_count=0)
        assert should_retry(parsed, "strict", 0, 3) is True

    def test_critical_only_skips_non_critical(self):
        parsed = self._parsed(approved=False, critical_count=0)
        assert should_retry(parsed, "critical_only", 0, 3) is False

    def test_critical_only_retries_on_critical(self):
        parsed = self._parsed(approved=False, critical_count=1)
        assert should_retry(parsed, "critical_only", 0, 3) is True


class TestBuildFixInstruction:
    def test_strict_includes_all(self):
        parsed = {
            "issues": [
                {"severity": "critical", "description": "SQL injection", "file": "app.py"},
                {"severity": "minor", "description": "Naming", "file": "utils.py"},
            ],
            "critical": [
                {"severity": "critical", "description": "SQL injection", "file": "app.py"}
            ],
            "suggestions": ["Add tests"],
        }
        result = build_fix_instruction(parsed, "strict")
        assert "SQL injection" in result
        assert "Naming" in result
        assert "Add tests" in result
        assert "app.py" in result
        assert "utils.py" in result

    def test_critical_only_filters(self):
        parsed = {
            "issues": [
                {"severity": "critical", "description": "SQL injection", "file": "app.py"},
                {"severity": "minor", "description": "Naming", "file": "utils.py"},
            ],
            "critical": [
                {"severity": "critical", "description": "SQL injection", "file": "app.py"}
            ],
            "suggestions": ["Add tests"],
        }
        result = build_fix_instruction(parsed, "critical_only")
        assert "SQL injection" in result
        assert "Naming" not in result
        assert "Add tests" not in result


class TestRecordIteration:
    def test_first_iteration(self):
        review_result: dict = {}
        parsed = {
            "approved": False,
            "issues": [{"severity": "critical", "description": "bug"}],
            "critical": [{"severity": "critical", "description": "bug"}],
            "suggestions": [],
        }
        result = record_iteration(review_result, 1, parsed, True, "fix it", None)
        assert len(result["iterations"]) == 1
        entry = result["iterations"][0]
        assert entry["attempt"] == 1
        assert entry["approved"] is False
        assert entry["critical_count"] == 1
        assert entry["fix_applied"] is True

    def test_tracks_fixed_issues(self):
        review_result: dict = {"iterations": [{"attempt": 1}]}
        prev = [{"description": "bug1"}, {"description": "bug2"}]
        parsed = {
            "approved": True,
            "issues": [],
            "critical": [],
            "suggestions": [],
        }
        result = record_iteration(review_result, 2, parsed, False, None, prev)
        entry = result["iterations"][-1]
        assert entry["issues_fixed_count"] == 2
        assert entry["issues_remaining_count"] == 0


class TestBuildReviewPrompt:
    def test_basic_format(self):
        template = "Title: {title}\nDesc: {description}\nFiles: {files_changed}\nDiff: {diff_text}"
        result = build_review_prompt(template, "My Task", "Do stuff", ["a.py", "b.py"], "diff here")
        assert "My Task" in result
        assert "a.py" in result
        assert "diff here" in result
