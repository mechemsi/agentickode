# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for the pr_fetch phase (PR diff/comment retrieval)."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.worker.phases import pr_fetch

_DIFF = """diff --git a/foo/bar.py b/foo/bar.py
index abc..def 100644
--- a/foo/bar.py
+++ b/foo/bar.py
@@ -1 +1 @@
-old
+new
diff --git a/baz.txt b/baz.txt
index 111..222 100644
--- a/baz.txt
+++ b/baz.txt
@@ -1 +1 @@
-a
+b
"""


class TestPrFetch:
    async def test_parses_changed_files_for_reviewer(
        self, db_session, make_task_run, mock_services, seed_proj1
    ):
        run = make_task_run(
            git_provider="github",
            repo_owner="o",
            repo_name="r",
            task_source_meta={"pr_number": 7},
        )
        db_session.add(run)
        await db_session.commit()

        provider = MagicMock()
        provider.get_pr_diff = AsyncMock(return_value=_DIFF)
        provider.get_pr_comments = AsyncMock(return_value=[])

        with (
            patch(
                "backend.worker.phases.pr_fetch.get_project_token",
                new=AsyncMock(return_value="tok"),
            ),
            patch("backend.worker.phases.pr_fetch.get_http_client", new=MagicMock()),
            patch(
                "backend.worker.phases.pr_fetch.get_git_provider",
                new=MagicMock(return_value=provider),
            ),
            patch(
                "backend.worker.phases.pr_fetch.broadcaster",
                new=MagicMock(log=AsyncMock()),
            ),
        ):
            result = await pr_fetch.run(run, db_session, mock_services)

        assert result["files_changed"] == ["foo/bar.py", "baz.txt"]
        # reviewing derives its file list from coding_results["results"][*]["files_changed"]
        assert run.coding_results["results"][0]["files_changed"] == ["foo/bar.py", "baz.txt"]
