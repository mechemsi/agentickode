# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-03-12

### Changed
- Renamed project from AutoDev to AgenticKode
- Updated all branding, screenshots, and documentation

## [0.1.0] - 2026-03-11

### Added
- Initial open-source release
- 8-phase worker pipeline (workspace_setup, init, planning, coding, testing, reviewing, approval, finalization)
- Multi-provider git integration (GitHub, Gitea, GitLab, Bitbucket)
- Pluggable AI agents (Claude CLI, OpenAI Codex, GitHub Copilot, Google Gemini, Aider, Kimi, OpenCode, OpenHands)
- Remote workspace servers with SSH-based execution
- Workflow templates with label-based routing
- Per-project instructions and encrypted secrets
- Real-time UI with WebSocket log streaming and SSE dashboard updates
- SSH terminal bridge via xterm.js
- Notifications (Slack, Discord, Telegram, webhook)
- Webhook task sources (Plane, GitHub, Gitea, GitLab)
- Cost tracking with per-invocation token counting
- Backup/export with optional AES encryption
- GPU dashboard for Ollama server monitoring
- Comparison mode for parallel agent evaluation
- Role configs with per-agent prompt overrides
