# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import UTC, datetime

from backend.services.cron_parser import human_readable, next_occurrence, validate_cron


class TestValidateCron:
    def test_valid_expressions(self):
        assert validate_cron("0 3 * * *") is True
        assert validate_cron("*/5 * * * *") is True
        assert validate_cron("0 0 * * 1") is True
        assert validate_cron("0 9-17 * * 1-5") is True

    def test_invalid_expressions(self):
        assert validate_cron("not a cron") is False
        assert validate_cron("") is False
        assert validate_cron("60 * * * *") is False


class TestNextOccurrence:
    def test_daily_at_three(self):
        base = datetime(2026, 3, 28, 1, 0, tzinfo=UTC)
        result = next_occurrence("0 3 * * *", base)
        assert result.hour == 3
        assert result.day == 28

    def test_next_occurrence_after_time(self):
        base = datetime(2026, 3, 28, 4, 0, tzinfo=UTC)
        result = next_occurrence("0 3 * * *", base)
        assert result.day == 29  # next day since 3 AM already passed

    def test_every_five_minutes(self):
        base = datetime(2026, 3, 28, 12, 0, tzinfo=UTC)
        result = next_occurrence("*/5 * * * *", base)
        assert result.minute == 5
        assert result.hour == 12

    def test_result_is_utc(self):
        result = next_occurrence("0 0 * * *")
        assert result.tzinfo == UTC


class TestHumanReadable:
    def test_daily_with_hour(self):
        assert "3:00" in human_readable("0 3 * * *")

    def test_every_hour(self):
        assert human_readable("0 * * * *") == "Every hour"

    def test_complex_returns_raw(self):
        expr = "0 9-17 * * 1-5"
        assert human_readable(expr) == expr

    def test_invalid_parts_returns_raw(self):
        assert human_readable("not valid") == "not valid"
