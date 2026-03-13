# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    """Extract first JSON object from LLM response text.

    Tries multiple strategies:
    1. Extract from markdown code blocks (```json ... ```)
    2. Find outermost { ... } braces
    """
    # Strategy 1: markdown code block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        block = m.group(1).strip()
        if block.startswith("{"):
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                pass

    # Strategy 2: first { to last }
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        return json.loads(text[json_start:json_end])
    raise ValueError("No JSON object found in response")
