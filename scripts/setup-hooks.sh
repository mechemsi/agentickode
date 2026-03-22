#!/usr/bin/env bash
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com
#
# Install git hooks. Called automatically by:
#   - npm postinstall (frontend/package.json)
#   - pip post-install via Makefile target
#   - manually: ./scripts/setup-hooks.sh

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
    echo "Not in a git repository — skipping hook install"
    exit 0
fi

HOOKS_DIR="$REPO_ROOT/.git/hooks"
SCRIPT_DIR="$REPO_ROOT/scripts"

# Install pre-commit hook
if [ -f "$SCRIPT_DIR/pre-commit" ]; then
    cp "$SCRIPT_DIR/pre-commit" "$HOOKS_DIR/pre-commit"
    chmod +x "$HOOKS_DIR/pre-commit"
    echo "✓ Installed pre-commit hook"
else
    echo "⚠ pre-commit script not found at $SCRIPT_DIR/pre-commit"
fi
