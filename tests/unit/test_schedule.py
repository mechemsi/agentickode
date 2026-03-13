# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.schedule.is_within_schedule."""

from datetime import UTC, datetime

from backend.services.schedule import is_within_schedule


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestIsWithinSchedule:
    """Test suite for the schedule utility."""

    def test_none_schedule_allows(self):
        assert is_within_schedule(None) is True

    def test_empty_dict_allows(self):
        assert is_within_schedule({}) is True

    def test_disabled_schedule_allows(self):
        schedule = {"enabled": False, "timezone": "UTC", "days": {}}
        assert is_within_schedule(schedule) is True

    def test_missing_enabled_key_allows(self):
        schedule = {"timezone": "UTC", "days": {}}
        assert is_within_schedule(schedule) is True

    def test_no_days_key_allows(self):
        schedule = {"enabled": True, "timezone": "UTC"}
        assert is_within_schedule(schedule) is True

    def test_empty_days_blocks(self):
        """Enabled schedule with empty days dict means all days disabled → blocks."""
        schedule = {"enabled": True, "timezone": "UTC", "days": {}}
        assert is_within_schedule(schedule) is False

    def test_within_normal_window(self):
        """Time inside a normal (non-overnight) window should allow."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": {"start": "09:00", "end": "17:00"}},  # Monday
        }
        # Monday 12:00 UTC
        now = _utc(2026, 3, 2, 12, 0)  # 2026-03-02 is a Monday
        assert is_within_schedule(schedule, now) is True

    def test_outside_normal_window_before(self):
        """Time before a normal window should block."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": {"start": "09:00", "end": "17:00"}},
        }
        now = _utc(2026, 3, 2, 8, 0)
        assert is_within_schedule(schedule, now) is False

    def test_outside_normal_window_after(self):
        """Time after a normal window should block."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": {"start": "09:00", "end": "17:00"}},
        }
        now = _utc(2026, 3, 2, 17, 30)
        assert is_within_schedule(schedule, now) is False

    def test_overnight_window_before_midnight(self):
        """Overnight window: time after start (before midnight) should allow."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": {"start": "20:00", "end": "08:00"}},
        }
        now = _utc(2026, 3, 2, 22, 0)  # Monday 22:00
        assert is_within_schedule(schedule, now) is True

    def test_overnight_window_after_midnight(self):
        """Overnight window: time after midnight but before end should allow.

        Note: the "after midnight" part is checked against the NEXT day's key.
        For the overnight window on Monday (key "0"), 02:00 on Tuesday checks
        against Tuesday's schedule (key "1"). This test verifies that if
        Tuesday also has a 20:00-08:00 window, 02:00 is within it.
        """
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {
                "0": {"start": "20:00", "end": "08:00"},
                "1": {"start": "20:00", "end": "08:00"},  # Tuesday
            },
        }
        now = _utc(2026, 3, 3, 2, 0)  # Tuesday 02:00
        assert is_within_schedule(schedule, now) is True

    def test_overnight_window_outside(self):
        """Overnight window: time between end and start should block."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": {"start": "20:00", "end": "08:00"}},
        }
        now = _utc(2026, 3, 2, 12, 0)  # Monday noon
        assert is_within_schedule(schedule, now) is False

    def test_day_disabled_null(self):
        """Day set to null should block."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": None},
        }
        now = _utc(2026, 3, 2, 12, 0)
        assert is_within_schedule(schedule, now) is False

    def test_day_missing_blocks(self):
        """Day key not present at all should block (not configured = disabled)."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"1": {"start": "00:00", "end": "23:59"}},  # only Tuesday
        }
        now = _utc(2026, 3, 2, 12, 0)  # Monday
        assert is_within_schedule(schedule, now) is False

    def test_timezone_conversion(self):
        """Schedule in Europe/Vilnius should convert UTC time correctly.

        Europe/Vilnius is UTC+2 in winter (EET).
        If schedule says Mon 10:00-18:00 Vilnius time, and it's Mon 09:00 UTC
        (= 11:00 Vilnius), that should be within the window.
        """
        schedule = {
            "enabled": True,
            "timezone": "Europe/Vilnius",
            "days": {"0": {"start": "10:00", "end": "18:00"}},
        }
        now = _utc(2026, 3, 2, 9, 0)  # 09:00 UTC = 11:00 Vilnius (EET, UTC+2)
        assert is_within_schedule(schedule, now) is True

    def test_timezone_conversion_outside(self):
        """UTC time that maps outside Vilnius window should block."""
        schedule = {
            "enabled": True,
            "timezone": "Europe/Vilnius",
            "days": {"0": {"start": "10:00", "end": "18:00"}},
        }
        now = _utc(2026, 3, 2, 7, 0)  # 07:00 UTC = 09:00 Vilnius
        assert is_within_schedule(schedule, now) is False

    def test_invalid_timezone_fail_open(self):
        """Invalid timezone should fail-open (allow dispatch)."""
        schedule = {
            "enabled": True,
            "timezone": "Fake/Timezone",
            "days": {"0": None},
        }
        now = _utc(2026, 3, 2, 12, 0)
        assert is_within_schedule(schedule, now) is True

    def test_all_day_window(self):
        """Window 00:00 to 23:59 should allow all day."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"5": {"start": "00:00", "end": "23:59"}},
        }
        now = _utc(2026, 3, 7, 15, 30)  # Saturday
        assert is_within_schedule(schedule, now) is True

    def test_exactly_at_start_inclusive(self):
        """Time exactly at start should be allowed (inclusive)."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": {"start": "09:00", "end": "17:00"}},
        }
        now = _utc(2026, 3, 2, 9, 0)
        assert is_within_schedule(schedule, now) is True

    def test_exactly_at_end_exclusive(self):
        """Time exactly at end should be blocked (exclusive)."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": {"start": "09:00", "end": "17:00"}},
        }
        now = _utc(2026, 3, 2, 17, 0)
        assert is_within_schedule(schedule, now) is False

    def test_malformed_time_fail_open(self):
        """Missing start/end keys should fail-open."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": {"start": "bad"}},
        }
        now = _utc(2026, 3, 2, 12, 0)
        assert is_within_schedule(schedule, now) is True

    def test_malformed_day_config_fail_open(self):
        """Non-dict day config (not null) should fail-open."""
        schedule = {
            "enabled": True,
            "timezone": "UTC",
            "days": {"0": "invalid"},
        }
        now = _utc(2026, 3, 2, 12, 0)
        assert is_within_schedule(schedule, now) is True

    def test_full_weekly_schedule(self):
        """Realistic full-week overnight schedule."""
        schedule = {
            "enabled": True,
            "timezone": "Europe/Vilnius",
            "days": {
                "0": {"start": "20:00", "end": "08:00"},
                "1": {"start": "20:00", "end": "08:00"},
                "2": {"start": "20:00", "end": "08:00"},
                "3": {"start": "20:00", "end": "08:00"},
                "4": {"start": "20:00", "end": "08:00"},
                "5": {"start": "00:00", "end": "23:59"},
                "6": {"start": "00:00", "end": "23:59"},
            },
        }
        # Monday 21:00 Vilnius = 19:00 UTC (EET, UTC+2) → within 20:00-08:00
        assert is_within_schedule(schedule, _utc(2026, 3, 2, 19, 0)) is True
        # Monday 15:00 Vilnius = 13:00 UTC → outside 20:00-08:00
        assert is_within_schedule(schedule, _utc(2026, 3, 2, 13, 0)) is False
        # Saturday 12:00 Vilnius = 10:00 UTC → within 00:00-23:59
        assert is_within_schedule(schedule, _utc(2026, 3, 7, 10, 0)) is True
