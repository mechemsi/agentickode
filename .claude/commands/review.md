# /review — Code Review

Perform a thorough code review of the specified file or recent changes.

## Steps
1. Read the target file(s) or run `git diff HEAD~1` for recent changes
2. Check against `.claude/rules/code-style.md`
3. Check against `.claude/rules/api-conventions.md`
4. Look for:
   - Security issues (SSH injection, XSS, hardcoded secrets)
   - SOLID violations (direct API calls bypassing Protocols, inline DB queries)
   - Missing license headers
   - Async/await correctness (missing await, blocking calls in async)
   - Type safety gaps (missing type hints, Any types)
   - Missing or inadequate error handling
   - Test coverage gaps
5. Output a structured report:
   - **Critical** — must fix before merge
   - **Warning** — should fix, explains why
   - **Suggestion** — optional improvement
6. For each issue, show the problematic code and a corrected version

## Usage
```
/review backend/api/runs.py
/review frontend/src/pages/Dashboard.tsx
/review  # reviews staged git changes
```
