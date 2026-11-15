---
title: Python major dependency upgrade review
status: implemented
date: 2026-11-15
related:
  - requirements.txt
  - tests/unit/test_mcp_server.py
---

# Python major dependency upgrade review

The supplied checkout already pins all five requested versions in requirements.txt,
with Redis compatibility changes and croniter regression tests. No Python lock file
exists. No pins or unrelated dependencies were changed during this review. Since all
targets were already present, validation used the combined target environment rather
than replaying sequential upgrades from the old pins.

## Migration review

- croniter 4/5/6/7: read the [changelog and embedded migration guide](https://github.com/pallets-eco/croniter/blob/main/CHANGELOG.rst).
  Version 4 removed Sunday 7; 5.0.1 restored it. Version 6 changed timestamp conversion.
  Version 7 tightens syntax and corrects maximum-step/range/impossible-date behavior.
  The only direct use is services/cron_parser.py. Existing tests cover Sunday 7, UTC,
  stricter validation and 59/15. No affected expressions were found in application
  configuration. Stored production schedules were unavailable and require review
  for maximum-field steps and newly invalid syntax before rollout. The pre-existing
  python-dateutil>=4.0.0 floor remains; croniter declares no minimum itself.
- cryptography 43/44/45/46/47/48/49/50: read every major section of the
  [changelog](https://cryptography.io/en/50.0.2/changelog/), including inline replacements.
  Stricter parsers, SSH password error types, removed legacy algorithms/type aliases,
  PKCS7 error handling and higher runtime/build requirements do not affect our Fernet,
  SHA256 and PBKDF2HMAC calls in services/encryption.py and backup/secret_handler.py.
  Encryption and backup secret tests pass without changing stored formats or KDF parameters.
  AsyncSSH also consumes cryptography; live SSH was not tested.
- redis 6/7/8: read [6.0](https://github.com/redis/redis-py/releases/tag/v6.0.0),
  [7.0](https://github.com/redis/redis-py/releases/tag/v7.0.0),
  [8.0](https://github.com/redis/redis-py/releases/tag/v8.0.0),
  [8.1](https://github.com/redis/redis-py/releases/tag/v8.1.0) and the
  [response migration guide](https://github.com/redis/redis-py/blob/v8.0.0/specs/unified_responses_migration_guide.md).
  QueueService is the only direct client and already uses protocol=2 and aclose().
  Removed cluster/cache APIs are unused. TLS, timeout, pool and retry defaults changed;
  the queue has no blocking-pop commands and retains upstream connection defaults.
  Mocked queue tests pass; live Redis was not available.
- websockets 15/16/17: read the [changelog](https://websockets.readthedocs.io/en/stable/project/changelog.html).
  Proxy/keepalive defaults, Python floors, alias removals, header encoding and keyword-only
  flags were reviewed. No direct imports exist: FastAPI WebSocket routes use Uvicorn.
  Python >=3.11 is already declared. A real localhost Uvicorn handshake and echo passed.
- fastmcp 4: read [4.0](https://github.com/PrefectHQ/fastmcp/releases/tag/v4.0.0),
  [4.1.8](https://github.com/PrefectHQ/fastmcp/releases/tag/v4.1.8) and the
  [3-to-4 migration guide](https://gofastmcp.com/docs/getting-started/upgrading/from-fastmcp-3).
  MCP SDK v2, snake_case fields, httpx2, removed callbacks and deprecated APIs were reviewed.
  Our FastMCP/Context imports and add_tool calls remain supported. HTTP inside our tools
  remains on httpx, as permitted by the guide. Existing FastAPI/Pydantic floors admit
  required versions. FastMCP requires websockets>=15.0.1, so upgrade websockets first
  when replaying these upgrades. Matching fastmcp-slim and MCP v2 resolve transitively.
  New tests exercise actual Client tool discovery, Context injection and serialization.
  SSE application construction also succeeds; remote transport interoperability is untested.

## Validation

Executed outside Docker as requested, with Python 3.11.2 in a disposable venv:

- uv pip install -r requirements.txt -r requirements-dev.txt: installed 94 packages.
- uv pip check: all packages compatible.
- pytest tests/ -q: 1172 passed; five existing broadcaster AsyncMock warnings.
- New MCP tests plus secret-handler tests: 14 passed, including both new tests.
- ruff check backend/ tests/: passed. Format check: 399 files passed before the new test,
  which separately passed lint and formatting.
- pyright --pythonpath /w/.venv/bin/python backend/: zero errors/warnings. The initial
  invocation without the explicit interpreter failed to locate virtualenv imports.
- Localhost Uvicorn/websockets handshake and echo: passed with Uvicorn's legacy-backend
  deprecation warning.

Docker builds, PostgreSQL migrations, live Redis/SSH and remote MCP were not verified.
CI uses Python 3.12 and must run the applicable remaining checks on the PR.
