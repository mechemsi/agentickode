# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AgenticKode, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email: **info@mechemsi.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix timeline**: Depends on severity, typically within 30 days for critical issues

## Scope

The following are in scope:
- AgenticKode backend API
- AgenticKode frontend application
- Worker pipeline and phase execution
- SSH/workspace server interactions
- Authentication and authorization
- Data handling and encryption

The following are out of scope:
- Third-party AI agent vulnerabilities (Ollama, OpenHands, Claude CLI)
- Third-party git provider vulnerabilities (GitHub, GitLab, Gitea, Bitbucket)
- Issues in dependencies (report these to the upstream project)

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest main | Yes |
| Older releases | Best effort |

## Security Best Practices for Self-Hosting

- Never expose the AgenticKode API directly to the internet without authentication
- Use strong, unique values for all secrets in `.env`
- Run workspace servers with non-root worker users (built-in support)
- Keep Docker images and dependencies up to date
- Enable encrypted backups when exporting configuration
- Restrict SSH key access to only the workspace servers that need it
