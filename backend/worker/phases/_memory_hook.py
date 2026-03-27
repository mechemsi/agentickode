# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Post-pipeline hook to extract and store learnings from completed runs."""

import logging

from backend.models.runs import TaskRun
from backend.services.http_client import get_http_client
from backend.services.memory.learning_extractor import LearningExtractor
from backend.services.memory.org_memory import OrgMemoryService

logger = logging.getLogger("agentickode.memory.hook")


async def store_run_learnings(run: TaskRun) -> int:
    """Extract learnings from a completed run and store in org memory.

    Returns number of learnings stored.
    """
    try:
        run_data = {
            "id": run.id,
            "title": run.title,
            "description": run.description,
            "project_id": run.project_id,
            "review_result": run.review_result,
            "test_results": run.test_results,
            "planning_result": run.planning_result,
        }

        extractor = LearningExtractor()
        learnings = extractor.extract(run_data)

        if not learnings:
            return 0

        client = get_http_client()
        memory = OrgMemoryService(client)
        stored = await memory.store_run_learnings(
            [
                {"content": item.content, "namespace": item.namespace, "metadata": item.metadata}
                for item in learnings
            ]
        )

        if stored:
            logger.info("Stored %d learnings from run #%d", stored, run.id)
        return stored

    except Exception:
        logger.exception("Failed to extract learnings from run #%d", run.id)
        return 0
