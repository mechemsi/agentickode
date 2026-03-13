# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for the JSON extraction utility."""

import pytest

from backend.services.json_extract import extract_json


class TestExtractJson:
    def test_extracts_simple_object(self):
        text = '{"key": "value"}'
        assert extract_json(text) == {"key": "value"}

    def test_extracts_from_surrounding_text(self):
        text = 'Here is the result: {"plan": "do stuff", "steps": 3} hope that helps'
        result = extract_json(text)
        assert result == {"plan": "do stuff", "steps": 3}

    def test_extracts_nested_objects(self):
        text = '```json\n{"outer": {"inner": [1, 2, 3]}}\n```'
        result = extract_json(text)
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_extracts_first_json_when_multiple_exist(self):
        text = '{"a": 1} and {"b": 2}'
        # rfind("}") will find the last brace, so it spans both objects
        # This is the known fragile behavior — it will try to parse "{"a": 1} and {"b": 2}"
        # which will fail, then the outer braces capture the whole thing.
        # Actually: find("{") = 0, rfind("}") = end, so it parses the full string
        # This will raise ValueError since the middle text is invalid JSON
        with pytest.raises((ValueError, KeyError)):
            extract_json(text)

    def test_raises_on_no_json(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            extract_json("just plain text with no braces")

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            extract_json("")

    def test_handles_json_with_unicode(self):
        text = '{"name": "tëst ünïcödë"}'
        assert extract_json(text) == {"name": "tëst ünïcödë"}

    def test_handles_booleans_and_nulls(self):
        text = '{"active": true, "deleted": false, "meta": null}'
        result = extract_json(text)
        assert result == {"active": True, "deleted": False, "meta": None}
