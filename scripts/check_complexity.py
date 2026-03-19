# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com
"""Check cyclomatic complexity of Python files using radon.

Usage: python scripts/check_complexity.py <min_grade> [file1.py file2.py ...]

min_grade: Minimum grade to report (A-F). E.g., "C" reports C, D, E, F.
If files are provided, only those are checked. Otherwise checks all
files under the current directory.

Exit codes:
  0 — no functions at or above the threshold
  1 — at least one function at or above the threshold
"""

import subprocess
import sys


GRADE_ORDER = ["A", "B", "C", "D", "E", "F"]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: check_complexity.py <min_grade> [file1.py ...]")
        return 2

    min_grade = sys.argv[1].upper()
    if min_grade not in GRADE_ORDER:
        print(f"ERROR: invalid grade '{min_grade}'. Must be one of: {GRADE_ORDER}")
        return 2

    files = sys.argv[2:]

    # Build radon command
    cmd = ["python3", "-m", "radon", "cc", "--min", min_grade, "--show-complexity"]
    if files:
        cmd.extend(files)
    else:
        cmd.append(".")

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout.strip()

    if not output:
        print(f"All functions are below grade {min_grade}. No issues found.")
        return 0

    # Filter out empty lines and file headers with no results
    lines = output.splitlines()
    has_issues = False
    report_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # radon outputs file paths followed by indented function lines
        # Function lines contain the grade letter like " C (12)"
        report_lines.append(line)
        # Check if this line has a complexity grade at or above threshold
        for grade in GRADE_ORDER[GRADE_ORDER.index(min_grade) :]:
            if f" {grade} (" in line or f" {grade} " in line:
                has_issues = True
                break

    if not has_issues:
        print(f"All functions are below grade {min_grade}. No issues found.")
        return 0

    print(f"Functions at or above grade {min_grade}:\n")
    for line in report_lines:
        print(line)

    print(f"\nGrades: A (1-5) simple | B (6-10) well-structured | "
          f"C (11-15) slightly complex | D (16-20) more complex | "
          f"E (21-25) very complex | F (26+) unmaintainable")

    return 1


if __name__ == "__main__":
    sys.exit(main())
