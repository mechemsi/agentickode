
## 2026-03-25 — Didn't use skill-creator skill when creating skills
**What went wrong:** Created 6 autodev skills manually without invoking the `skill-creator:skill-creator` or `superpowers:writing-skills` skill first, which could have ensured better structure, triggering accuracy, and best practices.
**Rule for next time:** When creating or editing skills, always invoke the `superpowers:writing-skills` skill before writing any SKILL.md files.

## 2026-03-25 — Project IDs with slashes break non-:path routes
**What went wrong:** The workspace-readiness endpoint used `{project_id}` without `:path`, but project IDs can contain slashes (e.g., `viminkas/prestashop`). FastAPI rejected the encoded `%2F` as a 404.
**Rule for next time:** Always use `{project_id:path}` for project ID route parameters, since project IDs can contain slashes. Check existing routes for the pattern before adding new ones.
