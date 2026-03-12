# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Helper functions for the reviewing phase retry loop."""

from datetime import UTC, datetime
from typing import Any

from backend.services.html_to_text import html_to_text
from backend.services.json_extract import extract_json


def _truncate_diff_at_hunk(diff_text: str, max_chars: int = 10000) -> str:
    """Truncate diff at nearest hunk boundary instead of cutting mid-line."""
    if len(diff_text) <= max_chars:
        return diff_text

    # Find the last hunk header (@@ ... @@) before the limit
    truncated = diff_text[:max_chars]
    last_hunk = truncated.rfind("\n@@")
    if last_hunk > 0:
        truncated = truncated[: last_hunk + 1]

    # Count remaining hunks for summary
    remaining = diff_text[len(truncated) :]
    remaining_hunks = remaining.count("\n@@")
    remaining_files = remaining.count("\ndiff --git")
    summary_parts = []
    if remaining_files:
        summary_parts.append(f"{remaining_files} more files")
    if remaining_hunks:
        summary_parts.append(f"{remaining_hunks} more hunks")
    suffix = ", ".join(summary_parts) if summary_parts else "additional content"
    return f"{truncated}\n[truncated — {suffix}]"


def fetch_diff_text(pr_diff: str | None, diff_from_ssh: str | None) -> str:
    """Return the best available diff text."""
    if pr_diff:
        return pr_diff
    if diff_from_ssh:
        return diff_from_ssh
    return "(diff unavailable)"


def build_review_prompt(
    user_template: str,
    title: str,
    description: str,
    all_files: list[str],
    diff_text: str,
) -> str:
    """Format the review prompt from the template."""
    truncated_diff = _truncate_diff_at_hunk(diff_text, max_chars=10000)
    return user_template.format(
        title=title,
        description=html_to_text(description),
        files_changed="\n".join(all_files),
        diff_text=truncated_diff,
    )


def parse_review_response(response_text: str) -> dict[str, Any]:
    """Extract JSON review data from agent response.

    Returns dict with approved, issues, suggestions. Critical issues override
    approval to False.
    """
    try:
        review_data = extract_json(response_text)
    except ValueError:
        review_data = {
            "approved": False,
            "issues": [{"description": "Failed to parse review"}],
            "suggestions": [],
        }

    approved = review_data.get("approved", False)
    issues = review_data.get("issues", [])
    suggestions = review_data.get("suggestions", [])

    # Critical issues override approval
    critical = [i for i in issues if i.get("severity") == "critical"]
    if critical:
        approved = False

    return {
        "approved": approved,
        "issues": issues,
        "suggestions": suggestions,
        "critical": critical,
    }


def should_retry(
    parsed: dict[str, Any],
    strictness: str,
    retry_count: int,
    max_retries: int,
) -> bool:
    """Determine whether to retry with a fix.

    - 'strict': retry on any non-approved review
    - 'critical_only': retry only when critical issues exist (default/backward compat)
    """
    if parsed["approved"]:
        return False
    if retry_count >= max_retries:
        return False

    if strictness == "strict":
        return True
    # critical_only (default)
    return len(parsed["critical"]) > 0


def build_fix_instruction(parsed: dict[str, Any], strictness: str) -> str:
    """Build fix instruction for the coder agent.

    - 'strict': include ALL issues and suggestions
    - 'critical_only': include only critical issues
    """
    lines = ["## Fix Review Issues\n"]

    if strictness == "strict":
        for issue in parsed["issues"]:
            sev = issue.get("severity", "unknown")
            desc = issue.get("description", "")
            file = issue.get("file", "")
            prefix = f"[{sev}] " if sev else ""
            loc = f" ({file})" if file else ""
            lines.append(f"- {prefix}{desc}{loc}")
        if parsed["suggestions"]:
            lines.append("\n## Suggestions\n")
            for s in parsed["suggestions"]:
                lines.append(f"- {s}")
    else:
        for issue in parsed["critical"]:
            desc = issue.get("description", "")
            file = issue.get("file", "")
            loc = f" ({file})" if file else ""
            lines.append(f"- {desc}{loc}")

    fix_files = [
        i.get("file", "")
        for i in (parsed["issues"] if strictness == "strict" else parsed["critical"])
        if i.get("file")
    ]
    if fix_files:
        lines.append(f"\n## Files\n{', '.join(fix_files)}")

    return "\n".join(lines)


def record_iteration(
    review_result: dict[str, Any],
    attempt: int,
    parsed: dict[str, Any],
    fix_applied: bool,
    fix_instruction: str | None,
    prev_issues: list[dict] | None,
) -> dict[str, Any]:
    """Append an iteration entry to review_result and return it.

    Tracks issues_fixed_count by comparing to previous iteration's issues.
    """
    iterations = review_result.get("iterations", [])

    current_issues = parsed["issues"]
    critical_count = len(parsed["critical"])

    issues_fixed_count = 0
    issues_remaining_count = len(current_issues)
    if prev_issues is not None and attempt > 1:
        prev_descs = {i.get("description", "") for i in prev_issues}
        remaining_descs = {i.get("description", "") for i in current_issues}
        issues_fixed_count = len(prev_descs - remaining_descs)

    entry: dict[str, Any] = {
        "attempt": attempt,
        "approved": parsed["approved"],
        "issues": current_issues,
        "critical_count": critical_count,
        "fix_applied": fix_applied,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if fix_instruction:
        entry["fix_instruction"] = fix_instruction
    if attempt > 1:
        entry["issues_fixed_count"] = issues_fixed_count
        entry["issues_remaining_count"] = issues_remaining_count

    iterations.append(entry)
    review_result["iterations"] = iterations
    return review_result