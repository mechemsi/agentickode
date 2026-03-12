"""Check that Alembic migrations have exactly one head (no forks).

Parses migration files directly — no database connection needed.
Used in CI to prevent merging PRs that introduce multiple heads.
"""

import os
import re
import sys

VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def parse_migrations(versions_dir: str) -> dict[str, tuple[set[str], str]]:
    """Parse all migration files and return {revision: (parents, filename)}."""
    revisions: dict[str, tuple[set[str], str]] = {}

    for fname in os.listdir(versions_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(versions_dir, fname)
        content = open(path).read()

        # Match: revision = "abc123" or revision: str = "abc123"
        rev_match = re.search(r'^revision\b.*?["\']([^"\']+)["\']', content, re.MULTILINE)
        down_match = re.search(r"^down_revision\b.*?=\s*(.+?)$", content, re.MULTILINE)
        if not rev_match or not down_match:
            continue

        rev = rev_match.group(1)
        down_raw = down_match.group(1).strip()

        if "None" in down_raw:
            parents: set[str] = set()
        elif "(" in down_raw:
            parents = set(re.findall(r'["\']([^"\']+)["\']', down_raw))
        else:
            m = re.search(r'["\']([^"\']+)["\']', down_raw)
            parents = {m.group(1)} if m else set()

        revisions[rev] = (parents, fname)

    return revisions


def find_heads(revisions: dict[str, tuple[set[str], str]]) -> list[str]:
    """Find revisions that are not a parent of any other revision."""
    all_parents: set[str] = set()
    for parents, _ in revisions.values():
        all_parents.update(parents)
    return [r for r in revisions if r not in all_parents]


def main() -> int:
    versions_dir = os.path.normpath(VERSIONS_DIR)
    if not os.path.isdir(versions_dir):
        print(f"ERROR: versions directory not found: {versions_dir}")
        return 1

    revisions = parse_migrations(versions_dir)
    if not revisions:
        print("ERROR: no migration files found")
        return 1

    heads = find_heads(revisions)

    if len(heads) == 1:
        _, fname = revisions[heads[0]]
        print(f"OK: single head {heads[0]} ({fname})")
        return 0

    print(f"ERROR: {len(heads)} Alembic heads detected (expected 1):")
    for h in heads:
        _, fname = revisions[h]
        print(f"  - {h} ({fname})")
    print()
    print("Fix: run 'alembic merge heads -m merge_migrations' or rebase your migration.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
