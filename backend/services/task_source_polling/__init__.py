# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Issue polling task sources — pull-based fallback to webhooks."""

from backend.services.task_source_polling.factory import get_poller
from backend.services.task_source_polling.protocol import IssuePoller

__all__ = ["IssuePoller", "get_poller"]
