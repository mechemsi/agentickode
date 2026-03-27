# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from backend.services.monitoring.payload_parsers import (
    parse_datadog_payload,
    parse_grafana_payload,
    parse_pagerduty_payload,
    parse_sentry_payload,
)
from backend.services.monitoring.severity import meets_threshold


class TestSeverity:
    def test_error_meets_error(self):
        assert meets_threshold("error", "error") is True

    def test_critical_meets_error(self):
        assert meets_threshold("critical", "error") is True

    def test_warning_does_not_meet_error(self):
        assert meets_threshold("warning", "error") is False

    def test_info_meets_info(self):
        assert meets_threshold("info", "info") is True

    def test_case_insensitive(self):
        assert meets_threshold("ERROR", "error") is True


class TestSentryParser:
    def test_basic_sentry_issue(self):
        payload = {
            "data": {
                "issue": {
                    "title": "ZeroDivisionError: division by zero",
                    "level": "error",
                    "culprit": "api.views.calculate",
                    "url": "https://sentry.io/issues/123/",
                },
                "event": {
                    "exception": {
                        "values": [
                            {
                                "type": "ZeroDivisionError",
                                "value": "division by zero",
                                "stacktrace": {
                                    "frames": [
                                        {
                                            "filename": "views.py",
                                            "lineno": 42,
                                            "function": "calculate",
                                        },
                                    ]
                                },
                            }
                        ]
                    }
                },
                "project": {"slug": "backend"},
            }
        }
        event = parse_sentry_payload(payload)
        assert event.source == "sentry"
        assert event.severity == "error"
        assert "ZeroDivisionError" in event.title
        assert "views.py:42" in event.description
        assert event.project_hint == "backend"

    def test_sentry_minimal_payload(self):
        payload = {"message": "Test alert", "data": {}}
        event = parse_sentry_payload(payload)
        assert event.source == "sentry"
        assert event.title == "Test alert"
        assert event.severity == "error"  # default


class TestDatadogParser:
    def test_basic_datadog_alert(self):
        payload = {
            "title": "CPU usage above 90%",
            "alert_type": "error",
            "body": "Host web-01 CPU at 95%",
            "link": "https://app.datadoghq.com/monitors/123",
            "tags": "env:production,service:api",
        }
        event = parse_datadog_payload(payload)
        assert event.source == "datadog"
        assert event.severity == "error"
        assert "CPU usage" in event.title
        assert "95%" in event.description

    def test_datadog_warning(self):
        payload = {"title": "Disk space low", "alert_type": "warning"}
        event = parse_datadog_payload(payload)
        assert event.severity == "warning"


class TestGrafanaParser:
    def test_basic_grafana_alert(self):
        payload = {
            "title": "High error rate",
            "state": "alerting",
            "message": "Error rate > 5%",
            "ruleUrl": "https://grafana.example.com/alerting/123",
        }
        event = parse_grafana_payload(payload)
        assert event.source == "grafana"
        assert event.severity == "error"
        assert "High error rate" in event.title

    def test_grafana_resolved(self):
        payload = {"title": "Alert resolved", "state": "resolved"}
        event = parse_grafana_payload(payload)
        assert event.severity == "info"

    def test_grafana_unified_alerting(self):
        payload = {
            "title": "Alert firing",
            "status": "firing",
            "alerts": [
                {
                    "labels": {"alertname": "HighLatency"},
                    "annotations": {"summary": "P99 > 2s"},
                }
            ],
        }
        event = parse_grafana_payload(payload)
        assert "HighLatency" in event.description


class TestPagerDutyParser:
    def test_basic_pagerduty_incident(self):
        payload = {
            "event": {
                "data": {
                    "title": "Database connection timeout",
                    "urgency": "high",
                    "html_url": "https://pagerduty.com/incidents/ABC",
                    "description": "PostgreSQL connections exhausted",
                    "service": {"summary": "backend-api"},
                }
            }
        }
        event = parse_pagerduty_payload(payload)
        assert event.source == "pagerduty"
        assert event.severity == "critical"
        assert "Database connection" in event.title
        assert event.project_hint == "backend-api"

    def test_pagerduty_low_urgency(self):
        payload = {
            "event": {
                "data": {"title": "Log volume spike", "urgency": "low"},
                "summary": "Log volume spike",
            }
        }
        event = parse_pagerduty_payload(payload)
        assert event.severity == "warning"
