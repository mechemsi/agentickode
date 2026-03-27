# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from backend.services.memory.learning_extractor import LearningExtractor


class TestLearningExtractor:
    def test_extracts_from_review(self):
        extractor = LearningExtractor()
        run_data = {
            "id": 1,
            "title": "Add auth middleware",
            "project_id": "test/project",
            "review_result": {
                "summary": "Good implementation but missing rate limiting on login endpoint. " * 3
            },
            "test_results": None,
            "planning_result": None,
        }
        learnings = extractor.extract(run_data)
        assert len(learnings) >= 1
        assert learnings[0].namespace == "patterns"
        assert "rate limiting" in learnings[0].content

    def test_extracts_from_test_failures(self):
        extractor = LearningExtractor()
        run_data = {
            "id": 2,
            "title": "Fix login",
            "project_id": "test/project",
            "review_result": None,
            "test_results": {"failures": ["test_login_timeout: AssertionError"]},
            "planning_result": None,
        }
        learnings = extractor.extract(run_data)
        assert any(item.namespace == "errors" for item in learnings)

    def test_extracts_from_planning(self):
        extractor = LearningExtractor()
        run_data = {
            "id": 3,
            "title": "Refactor API",
            "project_id": "test/project",
            "review_result": None,
            "test_results": None,
            "planning_result": {"plan": "Step 1: Extract service layer. " * 10},
        }
        learnings = extractor.extract(run_data)
        assert any(item.namespace == "decisions" for item in learnings)

    def test_no_learnings_from_empty_run(self):
        extractor = LearningExtractor()
        run_data = {
            "id": 4,
            "title": "Simple task",
            "project_id": "test/project",
            "review_result": None,
            "test_results": None,
            "planning_result": None,
        }
        learnings = extractor.extract(run_data)
        assert learnings == []

    def test_short_review_skipped(self):
        extractor = LearningExtractor()
        run_data = {
            "id": 5,
            "title": "Tiny fix",
            "project_id": "test/project",
            "review_result": {"summary": "LGTM"},
            "test_results": None,
            "planning_result": None,
        }
        learnings = extractor.extract(run_data)
        assert not any(item.namespace == "patterns" for item in learnings)


class TestObsidianSplitByHeadings:
    def test_splits_markdown(self):
        from backend.services.memory.obsidian_sync import ObsidianSyncService

        service = ObsidianSyncService.__new__(ObsidianSyncService)
        content = (
            "# Intro\nSome intro text\n\n## Details\nDetail content\n\n## Conclusion\nFinal text"
        )
        sections = service.split_by_headings(content, "test.md")
        assert len(sections) == 3
        assert sections[0]["heading"] == "Intro"
        assert sections[1]["heading"] == "Details"
        assert sections[2]["heading"] == "Conclusion"
        assert all(s["path"] == "test.md" for s in sections)

    def test_handles_no_headings(self):
        from backend.services.memory.obsidian_sync import ObsidianSyncService

        service = ObsidianSyncService.__new__(ObsidianSyncService)
        content = "Just some plain text\nwith multiple lines"
        sections = service.split_by_headings(content)
        assert len(sections) == 1
        assert sections[0]["heading"] == "Introduction"

    def test_handles_empty_content(self):
        from backend.services.memory.obsidian_sync import ObsidianSyncService

        service = ObsidianSyncService.__new__(ObsidianSyncService)
        sections = service.split_by_headings("")
        assert sections == []
