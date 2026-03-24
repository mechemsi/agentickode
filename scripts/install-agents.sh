#!/usr/bin/env bash
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

# Install AI coding agents into the platform container.
# Used during Docker build to pre-install agents for the chat feature.
#
# Usage:
#   ./scripts/install-agents.sh [agent1 agent2 ...]
#   ./scripts/install-agents.sh              # install all agents
#   ./scripts/install-agents.sh claude codex # install specific agents
#
# Agents are installed to ~/.local/bin (or npm global prefix).
# Post-install steps (plugins, marketplaces) are skipped — those
# require API keys which aren't available at build time.

set -euo pipefail

export PATH="$HOME/.local/bin:$HOME/.local/share/claude/bin:$PATH"
export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# Agent install commands (from backend/seed/agent_settings.py)
install_claude() {
    echo "Installing Claude CLI..."
    curl -fsSL https://claude.ai/install.sh | bash
    grep -q '$HOME/.local/bin' ~/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    export PATH="$HOME/.local/bin:$PATH"
    # Register the AgenticKode platform MCP server
    AGENTICKODE_MCP_URL="${AGENTICKODE_URL:-http://localhost:8000}/mcp/sse"
    claude mcp add agentickode --transport sse "$AGENTICKODE_MCP_URL" 2>/dev/null || true
    echo "  Claude CLI installed: $(command -v claude || echo 'not found')"
    echo "  MCP server registered: $AGENTICKODE_MCP_URL"
}

install_codex() {
    echo "Installing OpenAI Codex CLI..."
    ARCH=$(uname -m)
    case "$ARCH" in aarch64|arm64) ARCH=aarch64;; x86_64|amd64) ARCH=x86_64;; esac
    URL="https://github.com/openai/codex/releases/latest/download/codex-${ARCH}-unknown-linux-musl.tar.gz"
    curl -fsSL "$URL" -o /tmp/codex.tar.gz
    tar -xzf /tmp/codex.tar.gz -C /tmp
    mkdir -p "$HOME/.local/bin"
    mv "/tmp/codex-${ARCH}-unknown-linux-musl" "$HOME/.local/bin/codex"
    chmod +x "$HOME/.local/bin/codex"
    rm -f /tmp/codex.tar.gz
    echo "  Codex installed: $(command -v codex || echo 'not found')"
}

install_gemini() {
    echo "Installing Google Gemini CLI..."
    mkdir -p "$HOME/.local"
    npm install -g @google/gemini-cli --prefix "$HOME/.local"
    echo "  Gemini installed: $(command -v gemini || echo 'not found')"
}

install_aider() {
    echo "Installing Aider..."
    curl -fsSL https://aider.chat/install.sh | sh
    echo "  Aider installed: $(command -v aider || echo 'not found')"
}

install_opencode() {
    echo "Installing OpenCode..."
    curl -fsSL https://opencode.ai/install | bash
    echo "  OpenCode installed: $(command -v opencode || echo 'not found')"
}

install_kimi() {
    echo "Installing Kimi CLI..."
    curl -L code.kimi.com/install.sh | bash
    echo "  Kimi installed: $(command -v kimi || echo 'not found')"
}

install_copilot() {
    echo "Installing GitHub Copilot CLI..."
    curl -fsSL https://gh.io/copilot-install | bash
    echo "  Copilot installed: $(command -v copilot || echo 'not found')"
}

# Default: install all CLI agents
ALL_AGENTS="claude codex gemini aider opencode kimi copilot"
AGENTS="${*:-$ALL_AGENTS}"

echo "=== Installing AI agents: $AGENTS ==="
echo ""

for agent in $AGENTS; do
    if type "install_$agent" &>/dev/null; then
        install_"$agent" || echo "  WARNING: Failed to install $agent (continuing)"
        echo ""
    else
        echo "  Unknown agent: $agent (skipping)"
    fi
done

echo "=== Agent installation complete ==="
echo "Installed agents:"
for agent in $AGENTS; do
    check_cmd=""
    case "$agent" in
        claude)   check_cmd="claude" ;;
        codex)    check_cmd="codex" ;;
        gemini)   check_cmd="gemini" ;;
        aider)    check_cmd="aider" ;;
        opencode) check_cmd="opencode" ;;
        kimi)     check_cmd="kimi" ;;
        copilot)  check_cmd="copilot" ;;
    esac
    if [ -n "$check_cmd" ] && command -v "$check_cmd" &>/dev/null; then
        echo "  ✓ $agent ($(command -v "$check_cmd"))"
    else
        echo "  ✗ $agent (not found)"
    fi
done
