---
title: Python major dependency upgrades
status: implemented
date: 2026-11-15
related: [dependency-audit-2026-11-14.md]
---

# Python major dependency upgrades

Pinned the requested versions in requirements.txt, in this order: croniter 7.0.0,
cryptography 50.0.2, redis 8.1.0, fastmcp 4.1.8, websockets 17.4. Installed the
requirements with uv after each edit and ran the relevant checks. There is no
Python lock file in this repository; these exact pins replace its previous
minimum constraints. FastMCP's starting declaration was already >=4.0.0 rather
than the supplied 3.0.0. No other direct dependency constraints changed.

## Release and migration review

- croniter 4, 5, 6, 7: reviewed the [upstream changelog, including Upgrading to 7.0](https://github.com/pallets-eco/croniter/blob/main/CHANGELOG.rst).
  Version 4 removed Sunday alias 7, 5.0.1 restored it, and 6 changed timestamp
  conversion (later 6.x rewrote DST handling). Version 7 rejects non-ASCII cron
  digits/whitespace and invalid nth-weekday values, corrects maximum-field steps,
  and changes expand_from_start_time range handling. The application uses default
  UTC iteration, not that flag or the changed max_years_between_matches argument.
  Existing parser and scheduler tests pass; added five parser regression cases
  for validation, maximum-minute steps and Sunday 7. No checked-in schedule
  requiring rewriting was found.
- cryptography 43 through 50: reviewed each major section of the
  [upstream changelog](https://cryptography.io/en/latest/changelog/), which includes
  the replacement guidance for removed APIs. Version 43 raises OpenSSL/LibreSSL
  and RSA key-size floors and moves legacy ciphers; 44 raises LibreSSL support
  floors and tightens X.509 parsing; 45 changes SSH key password exceptions;
  46 removes Python 3.7, old ciphers and CSR accessors; 47 removes binary curves
  and OpenSSL 1.1 support and changes key-loading/serialization exceptions;
  48 removes Python 3.8 and rejects inconsistent CRLs; 49 removes old type aliases
  and some platform support and changes ChaCha20 counters; 50 deprecates FFDH
  and tightens malformed key/certificate parsing. Direct uses in encryption.py
  and backup/secret_handler.py are Fernet, SHA256 and PBKDF2HMAC, which retain
  their APIs. Encryption, instruction-injection and backup tests pass without
  changing keys, ciphertext format or KDF parameters.
- redis 6, 7, 8: reviewed releases [6.0.0](https://github.com/redis/redis-py/releases/tag/v6.0.0),
  [7.0.0](https://github.com/redis/redis-py/releases/tag/v7.0.0),
  [8.0.0](https://github.com/redis/redis-py/releases/tag/v8.0.0),
  [8.1.0](https://github.com/redis/redis-py/releases/tag/v8.1.0), and the
  [response migration guide](https://redis.readthedocs.io/en/stable/unified_responses.html).
  Version 6 changes TLS hostname checking and retry defaults and removes old
  constructor options; 7 removes async-cluster synchronous context management
  and changes helper/type surfaces. The standalone async queue uses none of those
  removed APIs. Version 8 defaults to RESP3 and changes connection/retry defaults
  and async type annotations. QueueService.connect now explicitly selects
  protocol=2 to preserve its wire protocol and response behavior. It already uses
  aclose(). No unified response mode is enabled. New timeout, pool and retry
  defaults remain in effect; no blocking pop commands are used.
- FastMCP 4: reviewed [4.0.0 release notes](https://github.com/PrefectHQ/fastmcp/releases/tag/v4.0.0),
  [4.1.8 release notes](https://github.com/PrefectHQ/fastmcp/releases/tag/v4.1.8), and
  [the 3-to-4 migration guide](https://gofastmcp.com/getting-started/upgrading/from-fastmcp-3).
  MCP SDK 2, snake_case protocol fields, removed server sampling/roots and
  deprecated APIs, sessionless negotiation, background-task extensions and
  httpx2 were checked against server.py and all eight tool modules. No removed
  API is used. The tools' own httpx REST calls remain valid. Existing FastAPI
  and Pydantic minimums already satisfy the new floors. The package manager
  installs the required fastmcp-slim==4.1.8 peer automatically; MCP 2 and other
  transitive dependencies are resolved from FastMCP's metadata.
- websockets 15, 16, 17: reviewed the [changelog](https://github.com/python-websockets/websockets/blob/main/docs/project/changelog.rst)
  and [asyncio migration guide](https://websockets.readthedocs.io/en/stable/howto/upgrade.html).
  Version 15 enables automatic client proxies and threaded keepalive; 16 requires
  Python 3.10; 17 requires Python 3.11, removes old module aliases, makes boolean
  arguments keyword-only and changes handshake/header handling. Version 17.4
  limits received message fragments. Project Python >=3.11 already meets this.
  There are no direct websockets imports: API handlers use FastAPI WebSocket,
  with Uvicorn providing transport. No application call-site changes are needed.

## Validation

Python 3.11.2 in an isolated virtual environment, without Docker:

- uv pip install -r requirements.txt -r requirements-dev.txt: passed; requirements
  reinstalled after each package edit. Final uv pip check: passed.
- Cron parser and both scheduler modules: 30 passed.
- Encryption, instruction injection and export modules: 16 passed.
- Redis queue module: 11 passed.
- Full pytest tests/: 1,172 passed in 33.71 seconds, five existing unawaited
  AsyncMock warnings from test_broadcaster.py, also recorded by the prior audit.
- ruff check backend/ tests/: passed.
- ruff format --check backend/ tests/: 399 files already formatted.
- pyright --pythonpath <validation-venv>/bin/python backend/: zero errors/warnings.
- FastMCP in-process client: discovered all 46 tools, confirmed Context is absent
  from public input schemas, and called list_projects with mocked HTTP transport.
  SSE app construction exposes /sse and /messages.
- Real Redis async client construction and close: passed with protocol=2; ping
  mocked, so this does not verify a live Redis connection.
- Loopback Uvicorn server using its websockets transport and websockets 17.4
  client: handshake, text echo and clean close passed. Current Uvicorn warns that
  its legacy websockets implementation will eventually switch to Sans-I/O.

No Docker image build, PostgreSQL migrations, live Redis/SSH integrations, or
remote MCP SSE client exchange was verified here. Frontend files and dependencies
were unchanged; frontend checks were not run. CI uses Python 3.12 and runs the
full checks and database migration validation.

## Stored schedule audit before deployment

Production cron expressions were unavailable. Review stored schedules for maximum
field steps such as 59/15 or 6/1, non-ASCII characters, invalid nth-weekday values,
and schedules with no future match. Croniter 7 interprets maximum-field steps as
only that maximum; if the intent was every interval, rewrite as */step. Invalid
expressions must be corrected before execution. These data checks remain untested.
