# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Parse monitoring webhook payloads into a unified MonitoringEvent."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MonitoringEvent:
    """Normalized monitoring event from any provider."""

    source: str  # sentry, datadog, grafana, pagerduty
    title: str
    severity: str  # debug, info, warning, error, critical, fatal
    description: str
    url: str = ""
    project_hint: str = ""  # helps match to a ProjectConfig
    raw_data: dict = field(default_factory=dict)


def parse_sentry_payload(body: dict) -> MonitoringEvent:
    """Parse a Sentry webhook (issue alert or event alert)."""
    # Sentry sends different shapes for issue vs event alerts
    data = body.get("data", {})
    event = data.get("event", data)
    issue = data.get("issue", {})

    title = issue.get("title") or event.get("title") or body.get("message", "Sentry alert")
    level = event.get("level") or issue.get("level") or "error"
    culprit = event.get("culprit") or issue.get("culprit", "")
    url = issue.get("url") or body.get("url", "")

    # Build description from stacktrace if available
    stacktrace_text = ""
    exception_values = (event.get("exception") or {}).get("values", [])
    for exc in exception_values[:2]:  # limit to first 2 exceptions
        exc_type = exc.get("type", "")
        exc_value = exc.get("value", "")
        stacktrace_text += f"{exc_type}: {exc_value}\n"
        frames = (exc.get("stacktrace") or {}).get("frames", [])
        for frame in frames[-5:]:  # last 5 frames
            filename = frame.get("filename", "")
            lineno = frame.get("lineno", "")
            function = frame.get("function", "")
            stacktrace_text += f"  {filename}:{lineno} in {function}\n"

    description = f"{title}\n\nCulprit: {culprit}\n"
    if stacktrace_text:
        description += f"\nStacktrace:\n{stacktrace_text}"
    if url:
        description += f"\nSentry URL: {url}"

    project_slug = (
        data.get("project", {}).get("slug", "")
        if isinstance(data.get("project"), dict)
        else body.get("project_slug", "")
    )

    return MonitoringEvent(
        source="sentry",
        title=title,
        severity=_normalize_severity(level),
        description=description,
        url=url,
        project_hint=project_slug,
        raw_data=body,
    )


def parse_datadog_payload(body: dict) -> MonitoringEvent:
    """Parse a Datadog webhook payload."""
    title = body.get("title") or body.get("event_title", "Datadog alert")
    alert_type = body.get("alert_type", "error")
    body_text = body.get("body") or body.get("event_msg", "")
    url = body.get("link") or body.get("event_url", "")
    tags = body.get("tags", "")

    severity_map = {"error": "error", "warning": "warning", "info": "info", "success": "info"}
    severity = severity_map.get(alert_type, "error")

    return MonitoringEvent(
        source="datadog",
        title=title,
        severity=severity,
        description=f"{title}\n\n{body_text}\n\nTags: {tags}",
        url=url,
        raw_data=body,
    )


def parse_grafana_payload(body: dict) -> MonitoringEvent:
    """Parse a Grafana webhook payload (unified alerting)."""
    title = body.get("title") or body.get("ruleName", "Grafana alert")
    state = body.get("state") or body.get("status", "alerting")
    message = body.get("message") or body.get("body", "")
    rule_url = body.get("ruleUrl") or body.get("externalURL", "")

    state_severity = {
        "alerting": "error",
        "firing": "error",
        "no_data": "warning",
        "pending": "warning",
        "ok": "info",
        "resolved": "info",
    }
    severity = state_severity.get(state.lower(), "error")

    # Grafana unified alerting format
    alerts = body.get("alerts", [])
    alert_details = ""
    for alert in alerts[:3]:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        alert_details += f"- {labels.get('alertname', 'unknown')}: "
        alert_details += f"{annotations.get('summary', annotations.get('description', ''))}\n"

    description = f"{title}\n\nState: {state}\n{message}"
    if alert_details:
        description += f"\n\nAlerts:\n{alert_details}"

    return MonitoringEvent(
        source="grafana",
        title=title,
        severity=severity,
        description=description,
        url=rule_url,
        raw_data=body,
    )


def parse_pagerduty_payload(body: dict) -> MonitoringEvent:
    """Parse a PagerDuty webhook v3 payload."""
    event = body.get("event", {})
    data = event.get("data", {})
    title = data.get("title") or event.get("summary", "PagerDuty incident")
    urgency = data.get("urgency", "high")
    html_url = data.get("html_url", "")
    description_text = data.get("description") or data.get("body", "")
    service_name = (data.get("service") or {}).get("summary", "")

    severity = "critical" if urgency == "high" else "warning"

    description = f"{title}\n\nService: {service_name}\n{description_text}"
    if html_url:
        description += f"\nPagerDuty: {html_url}"

    return MonitoringEvent(
        source="pagerduty",
        title=title,
        severity=severity,
        description=description,
        url=html_url,
        project_hint=service_name,
        raw_data=body,
    )


def _normalize_severity(level: str) -> str:
    """Normalize various severity strings to our standard set."""
    level = level.lower().strip()
    mapping = {
        "err": "error",
        "warn": "warning",
        "crit": "critical",
        "alert": "critical",
        "emergency": "fatal",
        "emerg": "fatal",
        "notice": "info",
    }
    return mapping.get(level, level)
