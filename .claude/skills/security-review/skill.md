# Skill: Security Review

**Type**: Auto-invoked workflow
**Triggers**: When asked to review code for security, before deploying auth/webhook code, or when the word "security" appears in a task

## Purpose
Perform a deep security audit of code changes or a specified module.

## Workflow

### Step 1 — Identify Scope
- If given a file: audit that file
- If given a PR/diff: audit all changed files
- If given a feature name: find all related files first

### Step 2 — Run Security Checklist

#### SSH & Remote Execution
- [ ] All SSH commands use `SSHService` — no direct subprocess calls
- [ ] Command arguments are properly escaped (no shell injection via user input)
- [ ] Workspace server operations validate server ownership before executing
- [ ] SSH key permissions are properly restricted (600)

#### Webhook Input Validation
- [ ] GitHub/Gitea/GitLab webhook signatures are verified
- [ ] Webhook payloads are validated with Pydantic schemas before processing
- [ ] Issue titles/descriptions are sanitized before use in shell commands or prompts
- [ ] Rate limiting on webhook endpoints

#### Secret Management
- [ ] No hardcoded secrets, API keys, or credentials anywhere
- [ ] All secrets accessed via environment variables or encrypted DB fields
- [ ] `encryption.py` AES keys are properly managed
- [ ] Backup export encrypts secrets when flag is set
- [ ] `.env` files are in `.gitignore`

#### API Security
- [ ] No inline SQLAlchemy queries — all through Repository pattern
- [ ] Pydantic schemas validate all request bodies
- [ ] Error messages don't leak stack traces or internal paths
- [ ] WebSocket connections validate session/auth

#### Agent Execution
- [ ] CLI commands built for agents don't allow injection via task descriptions
- [ ] Agent environment variables don't leak platform secrets
- [ ] Prompt injection via issue content is mitigated

#### Dependencies
- [ ] Run `pip audit` or check for known CVEs in Python deps
- [ ] Run `npm audit` for frontend deps
- [ ] No packages with known critical vulnerabilities

### Step 3 — Report
Output findings grouped by severity:
- **Critical** — exploitable vulnerability, block deploy
- **High** — serious risk, fix this sprint
- **Medium** — should fix, low exploitability
- **Info** — best practice suggestion

For each finding include:
1. What the vulnerability is
2. Where it exists (file + line)
3. How it could be exploited
4. The fix with code example
