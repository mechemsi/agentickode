# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Extract reusable learnings from completed task runs."""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("agentickode.memory.extractor")


@dataclass
class Learning:
    """A single learning extracted from a run."""

    content: str
    namespace: str = "general"
    metadata: dict = field(default_factory=dict)


class LearningExtractor:
    """Parse completed run data for patterns, decisions, and reusable insights."""

    def extract(self, run_data: dict) -> list[Learning]:
        """Extract learnings from a completed run's data.

        Args:
            run_data: Dict with keys like title, description, review_result,
                     test_results, coding_results, project_id, etc.

        Returns:
            List of Learning objects to store in org memory.
        """
        learnings: list[Learning] = []
        project_id = run_data.get("project_id", "")
        run_id = run_data.get("id", "")
        base_meta = {"project_id": project_id, "run_id": run_id}

        # Extract from review results
        review = run_data.get("review_result")
        if review and isinstance(review, dict):
            review_text = review.get("summary") or review.get("review", "")
            if review_text and len(review_text) > 50:
                learnings.append(
                    Learning(
                        content=f"Code review finding for {run_data.get('title', '')}:\n{review_text}",
                        namespace="patterns",
                        metadata={**base_meta, "source": "review"},
                    )
                )

        # Extract from test failures (what broke and how it was fixed)
        test_results = run_data.get("test_results")
        if test_results and isinstance(test_results, dict):
            failures = test_results.get("failures") or test_results.get("failed_tests", [])
            if failures:
                failure_text = str(failures)[:500]
                learnings.append(
                    Learning(
                        content=f"Test failures encountered in {run_data.get('title', '')}:\n{failure_text}",
                        namespace="errors",
                        metadata={**base_meta, "source": "testing"},
                    )
                )

        # Extract from planning results (architectural decisions)
        planning = run_data.get("planning_result")
        if planning and isinstance(planning, dict):
            plan_text = planning.get("plan") or planning.get("summary", "")
            if plan_text and len(plan_text) > 100:
                learnings.append(
                    Learning(
                        content=f"Implementation approach for {run_data.get('title', '')}:\n{plan_text[:800]}",
                        namespace="decisions",
                        metadata={**base_meta, "source": "planning"},
                    )
                )

        return learnings
