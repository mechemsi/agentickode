# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Seed data for CLI agent definitions (AgentSettings table)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models import AgentSettings
from backend.seed._helpers import commands_for

logger = logging.getLogger("agentickode.seed")

# ---------------------------------------------------------------------------
# Claude CLI install: binary + marketplaces + plugins
# ---------------------------------------------------------------------------

_CLAUDE_MARKETPLACES = [
    "anthropics/skills",
    "anthropics/claude-plugins-official",
    "affaan-m/everything-claude-code",
    "obra/superpowers-marketplace",
    "thedotmack/claude-mem",
]

_CLAUDE_PLUGINS = [
    # claude-plugins-official
    "agent-sdk-dev@claude-plugins-official",
    "claude-code-setup@claude-plugins-official",
    "claude-md-management@claude-plugins-official",
    "code-review@claude-plugins-official",
    "code-simplifier@claude-plugins-official",
    "commit-commands@claude-plugins-official",
    "context7@claude-plugins-official",
    "feature-dev@claude-plugins-official",
    "firecrawl@claude-plugins-official",
    "frontend-design@claude-plugins-official",
    "github@claude-plugins-official",
    "playground@claude-plugins-official",
    "playwright@claude-plugins-official",
    "qodo-skills@claude-plugins-official",
    "security-guidance@claude-plugins-official",
    "serena@claude-plugins-official",
    "skill-creator@claude-plugins-official",
    "superpowers@claude-plugins-official",
    # superpowers-marketplace
    "episodic-memory@superpowers-marketplace",
    "superpowers-developing-for-claude-code@superpowers-marketplace",
    # thedotmack
    "claude-mem@thedotmack",
    # anthropic-agent-skills
    "document-skills@anthropic-agent-skills",
    "example-skills@anthropic-agent-skills",
    # everything-claude-code
    "everything-claude-code@everything-claude-code",
]

# Extra tools installed after Claude plugins
_CLAUDE_POST_INSTALL = [
    "npx --yes get-shit-done-cc@latest --claude --global || true",
    "pipx install superclaude || true",
    "superclaude install || true",
    "superclaude mcp --servers sequential-thinking || true",
]

# Phase 1: Binary install only (no auth needed)
_CLAUDE_INSTALL_CMD = " && ".join(
    [
        "curl -fsSL https://claude.ai/install.sh | bash",
        "grep -q '$HOME/.local/bin' ~/.bashrc 2>/dev/null || echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc",
        'export PATH="$HOME/.local/bin:$PATH"',
        "mkdir -p ~/.ssh && ssh-keyscan -t ed25519 github.com gitlab.com bitbucket.org >> ~/.ssh/known_hosts 2>/dev/null || true",
        (
            "test -f ~/.ssh/id_ed25519 && "
            'export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new -o BatchMode=yes" '
            "|| true"
        ),
        "export GIT_TERMINAL_PROMPT=0",
        "git config --global http.sslVerify true 2>/dev/null || true",
        "export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt",
    ]
)

# Phase 2: Plugins & tools (requires auth/credentials)
_CLAUDE_POST_INSTALL_CMD = " && ".join(
    ['export PATH="$HOME/.local/bin:$PATH"']
    + ["export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt"]
    + [f"claude plugin marketplace add {m} || true" for m in _CLAUDE_MARKETPLACES]
    + [f"claude plugin install {p} || true" for p in _CLAUDE_PLUGINS]
    + _CLAUDE_POST_INSTALL
)


DEFAULT_AGENT_SETTINGS: list[dict] = [
    {
        "agent_name": "claude",
        "display_name": "Claude CLI",
        "description": "Anthropic Claude Code CLI agent",
        "supports_session": True,
        "default_timeout": 600,
        "max_retries": 1,
        "command_templates": commands_for("claude"),
        "agent_type": "cli_binary",
        "check_cmd": "command -v claude",
        "prereq_check": "command -v curl",
        "prereq_name": "curl",
        "install_cmd": _CLAUDE_INSTALL_CMD,
        "post_install_cmd": _CLAUDE_POST_INSTALL_CMD,
        "needs_non_root": True,
    },
    {
        "agent_name": "codex",
        "display_name": "OpenAI Codex CLI",
        "description": "OpenAI Codex CLI agent",
        "supports_session": False,
        "default_timeout": 600,
        "max_retries": 1,
        "command_templates": commands_for("codex"),
        "agent_type": "cli_binary",
        "check_cmd": "command -v codex",
        "prereq_check": "command -v curl && command -v tar",
        "prereq_name": "curl and tar",
        "install_cmd": (
            "ARCH=$(uname -m) && "
            'case "$ARCH" in aarch64|arm64) ARCH=aarch64;; x86_64|amd64) ARCH=x86_64;; esac && '
            'URL="https://github.com/openai/codex/releases/latest/download/'
            'codex-${ARCH}-unknown-linux-musl.tar.gz" && '
            'curl -fsSL "$URL" -o /tmp/codex.tar.gz && '
            "tar -xzf /tmp/codex.tar.gz -C /tmp && "
            'mkdir -p "$HOME/.local/bin" && '
            'mv /tmp/codex-${ARCH}-unknown-linux-musl "$HOME/.local/bin/codex" && '
            'chmod +x "$HOME/.local/bin/codex" && '
            "rm -f /tmp/codex.tar.gz"
        ),
        "needs_non_root": True,
    },
    {
        "agent_name": "gemini",
        "display_name": "Google Gemini CLI",
        "description": "Google Gemini CLI agent",
        "supports_session": False,
        "default_timeout": 600,
        "max_retries": 1,
        "command_templates": commands_for("gemini"),
        "agent_type": "cli_binary",
        "check_cmd": "command -v gemini",
        "prereq_check": "command -v npm",
        "prereq_name": "npm (Node.js 18+)",
        "install_cmd": (
            'mkdir -p "$HOME/.local" && '
            'npm install -g @google/gemini-cli --prefix "$HOME/.local"'
        ),
        "needs_non_root": True,
    },
    {
        "agent_name": "kimi",
        "display_name": "Kimi CLI",
        "description": "Moonshot Kimi CLI agent",
        "supports_session": False,
        "default_timeout": 600,
        "max_retries": 1,
        "command_templates": commands_for("kimi"),
        "agent_type": "cli_binary",
        "check_cmd": "command -v kimi",
        "prereq_check": "command -v curl",
        "prereq_name": "curl",
        "install_cmd": "curl -L code.kimi.com/install.sh | bash",
        "needs_non_root": True,
    },
    {
        "agent_name": "aider",
        "display_name": "Aider",
        "description": "Aider AI pair programming tool",
        "supports_session": False,
        "default_timeout": 600,
        "max_retries": 1,
        "command_templates": commands_for("aider"),
        "agent_type": "cli_binary",
        "check_cmd": "command -v aider",
        "prereq_check": "command -v curl",
        "prereq_name": "curl",
        "install_cmd": "curl -fsSL https://aider.chat/install.sh | sh",
        "needs_non_root": True,
    },
    {
        "agent_name": "opencode",
        "display_name": "OpenCode",
        "description": "OpenCode CLI agent",
        "supports_session": False,
        "default_timeout": 600,
        "max_retries": 1,
        "command_templates": commands_for("opencode"),
        "agent_type": "cli_binary",
        "check_cmd": "command -v opencode",
        "prereq_check": "command -v curl",
        "prereq_name": "curl",
        "install_cmd": "curl -fsSL https://opencode.ai/install | bash",
        "needs_non_root": True,
    },
    {
        "agent_name": "copilot",
        "display_name": "GitHub Copilot CLI",
        "description": "GitHub Copilot CLI terminal agent",
        "supports_session": False,
        "default_timeout": 600,
        "max_retries": 1,
        "command_templates": commands_for("copilot"),
        "agent_type": "cli_binary",
        "check_cmd": "command -v copilot",
        "prereq_check": "command -v curl",
        "prereq_name": "curl",
        "install_cmd": "curl -fsSL https://gh.io/copilot-install | bash",
        "needs_non_root": True,
    },
    {
        "agent_name": "openhands",
        "display_name": "OpenHands",
        "description": "Autonomous AI software engineer",
        "supports_session": False,
        "default_timeout": 600,
        "max_retries": 1,
        "command_templates": {},
        "agent_type": "api_service",
        "check_cmd": "curl -sf http://localhost:3000/api/health",
        "prereq_check": "command -v docker",
        "prereq_name": "docker",
        "install_cmd": "docker pull ghcr.io/all-hands-ai/openhands:latest",
        "needs_non_root": False,
    },
]

_INSTALL_FIELDS = (
    "agent_type",
    "install_cmd",
    "post_install_cmd",
    "check_cmd",
    "prereq_check",
    "prereq_name",
    "needs_non_root",
)


async def seed_agent_settings(db: AsyncSession) -> None:
    """Insert default agent settings if they don't exist.

    Also backfills empty command_templates and install metadata for
    existing rows so upgrades get the defaults populated in the UI.
    """
    created = 0
    backfilled = 0
    for defaults in DEFAULT_AGENT_SETTINGS:
        result = await db.execute(
            select(AgentSettings).where(AgentSettings.agent_name == defaults["agent_name"])
        )
        existing = result.scalar_one_or_none()
        if not existing:
            db.add(AgentSettings(**defaults))
            created += 1
        else:
            changed = False
            if not existing.command_templates and defaults.get("command_templates"):
                existing.command_templates = defaults["command_templates"]
                changed = True
            # Backfill install metadata for pre-015 rows
            for field in _INSTALL_FIELDS:
                if field in defaults and not getattr(existing, field, None):
                    setattr(existing, field, defaults[field])
                    changed = True
            # Split legacy combined install_cmd into install + post_install
            # for claude. If install_cmd contains marketplace/plugin commands,
            # it's the old combined format — replace with the split version.
            if (
                existing.agent_name == "claude"
                and existing.install_cmd
                and "install.sh" in existing.install_cmd
                and "marketplace" in existing.install_cmd
            ):
                existing.install_cmd = defaults.get("install_cmd", existing.install_cmd)
                existing.post_install_cmd = defaults.get("post_install_cmd")
                changed = True
            # Upgrade command_templates: add --output-format json to claude commands
            # Only upgrades commands that don't already have --output-format
            if (
                existing.agent_name == "claude"
                and existing.command_templates
                and defaults.get("command_templates")
            ):
                for key, new_val in defaults["command_templates"].items():
                    old_val = existing.command_templates.get(key, "")
                    if (
                        isinstance(old_val, str)
                        and "--output-format" not in old_val
                        and "--output-format" in str(new_val)
                    ):
                        existing.command_templates[key] = new_val  # type: ignore[index]
                        changed = True
                if changed:
                    flag_modified(existing, "command_templates")
            if changed:
                backfilled += 1
    await db.commit()
    if created:
        logger.info("Seeded %d agent settings", created)
    if backfilled:
        logger.info("Backfilled fields for %d agents", backfilled)
