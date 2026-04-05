# /fix-issue — Fix a GitHub Issue

Given an issue number or description, locate the bug and apply a fix.

## Steps
1. Read the issue description provided by the user
2. Search the codebase for relevant files (`Grep`, `Glob`, file reads)
3. Reproduce the logic of the bug mentally — trace the data flow
4. Propose a fix with explanation
5. Apply the fix
6. Write or update a test that would catch this regression
7. Run targeted checks:
   ```bash
   docker compose -f docker-compose.dev.yml exec backend ruff check backend/path/to/file.py --fix
   docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_affected.py -x -v
   ```
8. Summarize what was changed and why

## Usage
```
/fix-issue #42
/fix-issue "Webhook handler crashes when issue title contains special characters"
```

## Rules
- Do not change unrelated code
- Keep the fix minimal and focused
- Add a comment if the fix is non-obvious
- Include the license header on any new files
