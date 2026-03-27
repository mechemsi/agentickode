# Implementation Log

Persistent record of what was built, when, and by whom.

---

## 2026-03-28 — Autonomous Platform Integrations (v0.3.0+)

**Commit**: `8014f0f`
**Tests**: 69 added, 1147 total passing
**Files**: 57 changed (56 new, 4143 lines added)

### Phase 0: Run Factory Extraction
- Extracted `_create_task_run()` from `backend/api/webhooks.py` into shared `backend/services/run_factory.py`
- All webhook handlers and new sources reuse this factory

### Phase 1: Cron/Heartbeat Agent Scheduler
- `backend/worker/scheduler.py` — `TaskScheduler` polls `scheduled_tasks` table every 30s, dispatches due tasks as `TaskRun` rows
- `backend/services/cron_parser.py` — Validate, compute next occurrence, human-readable cron descriptions (wraps `croniter`)
- `backend/api/scheduled_tasks.py` — CRUD endpoints + manual trigger
- `backend/repositories/scheduled_task_repo.py` — `list_due()` with `FOR UPDATE SKIP LOCKED`
- `backend/mcp/tools/scheduling.py` — 4 MCP tools: list, create, update, trigger
- Dependency added: `croniter>=3.0.0`

### Phase 2: Event-Driven Auto-Dispatch Rules Engine
- `backend/models/automation_rules.py` — `AutomationRule` model with event_source, event_filter (JSONB), action_type, cooldown
- `backend/services/rules_engine.py` — `RulesEngine` matches events against rules, executes `create_run` actions
- `backend/services/rules_dispatcher.py` — `RulesDispatcher` subscribes to broadcaster global events
- `backend/api/automation_rules.py` — CRUD endpoints
- `backend/mcp/tools/automation.py` — 3 MCP tools: list, create, update
- Migration: `031_add_automation_rules.py`

### Phase 3: Monitoring Webhooks (Sentry/Datadog/Grafana/PagerDuty)
- `backend/api/webhooks_monitoring.py` — 4 webhook endpoints with deduplication
- `backend/services/monitoring/payload_parsers.py` — Provider-specific payload parsers into unified `MonitoringEvent`
- `backend/services/monitoring/severity.py` — Severity threshold comparison
- `backend/api/monitoring_rules.py` — CRUD for monitoring rules
- Migration: `032_monitoring_rule_enhancements.py` (dedup columns)

### Phase 4: Bidirectional Task Management
- `backend/services/task_management/protocol.py` — `TaskManager` protocol (update_status, add_comment, create_issue)
- `backend/services/task_management/github_manager.py` — Label-based status sync + issue creation
- `backend/services/task_management/plane_manager.py` — State group transitions via Plane API
- `backend/services/task_management/linear_manager.py` — GraphQL API with agent session tracking
- `backend/services/task_management/status_sync.py` — `StatusSyncer` listens to run events, updates external trackers
- `backend/api/webhooks_linear.py` — Linear issue webhook handler
- `backend/api/webhooks_pr_comment.py` — `@agentickode` PR comment → auto-response run
- Config: `linear_api_key`, `linear_webhook_secret`, `plane_api_url`, `plane_api_key`

### Phase 5: Bidirectional Messaging + Remote Agent Relay
- `backend/services/messaging/command_parser.py` — Parse "run myproject fix bug" → structured `Command`
- `backend/services/messaging/command_executor.py` — Execute commands using platform services
- `backend/services/messaging/agent_relay.py` — Bridge Slack/Discord ↔ running agents via tmux send-keys + capture-pane
- `backend/api/webhooks_slack.py` — Slack Events API + slash commands with signature verification
- `backend/api/webhooks_discord.py` — Discord Interactions endpoint
- Config: `slack_signing_secret`, `slack_bot_token`, `discord_public_key`, `discord_bot_token`

### Phase 6: Org-Level Memory + Obsidian Integration
- `backend/services/memory/org_memory.py` — `OrgMemoryService` stores/queries cross-project knowledge in ChromaDB `org_memory` collection
- `backend/services/memory/learning_extractor.py` — Extracts learnings from review results, test failures, planning decisions
- `backend/services/memory/obsidian_sync.py` — Read/write Obsidian vaults via Local REST API plugin
- `backend/api/memory.py` — Store, query, sync endpoints
- `backend/mcp/tools/memory.py` — 3 MCP tools: query_org_memory, store_knowledge, sync_obsidian_vault
- `backend/worker/phases/_memory_hook.py` — Post-pipeline hook for automatic learning extraction

### Background Services Added to Lifespan
- `TaskScheduler` — polls scheduled tasks
- `RulesDispatcher` — evaluates automation rules on events
- `StatusSyncer` — syncs run status to external task trackers
