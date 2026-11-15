---
title: Unmaintained dependency audit review
date: 2026-11-15
status: no-fix-available
---

# Unmaintained dependency audit review

No dependency versions or application code changed. Queried the PyPI JSON API for all 11 packages in the supplied issue. Every latest stable release has the same upload date reported by the audit and remains older than two years. There is no newer stable version that resolves these age flags. Release age alone does not establish a vulnerability.

| Package | Latest stable version | Release date |
|---------|-----------------------|--------------|
| [apeye](https://pypi.org/pypi/apeye/json) | 1.4.1 | 2023-08-14 |
| [apeye-core](https://pypi.org/pypi/apeye-core/json) | 1.1.5 | 2024-01-30 |
| [colorama](https://pypi.org/pypi/colorama/json) | 0.4.6 | 2022-10-25 |
| [defusedxml](https://pypi.org/pypi/defusedxml/json) | 0.7.1 | 2021-03-08 |
| [jsonref](https://pypi.org/pypi/jsonref/json) | 1.1.0 | 2023-01-16 |
| [mando](https://pypi.org/pypi/mando/json) | 0.8.2 | 2024-10-20 |
| [mdurl](https://pypi.org/pypi/mdurl/json) | 0.1.2 | 2022-08-14 |
| [natsort](https://pypi.org/pypi/natsort/json) | 8.4.0 | 2023-06-20 |
| [pip-requirements-parser](https://pypi.org/pypi/pip-requirements-parser/json) | 32.0.1 | 2022-12-21 |
| [radon](https://pypi.org/pypi/radon/json) | 6.0.1 | 2023-03-26 |
| [sortedcontainers](https://pypi.org/pypi/sortedcontainers/json) | 2.4.0 | 2021-05-16 |

Radon is already pinned to its latest version, 6.0.1. Its published requirement is `mando>=0.6,<0.8`, which resolves to 0.7.1. Mando 0.8.2 also exceeds the age threshold, so forcing an incompatible override would not resolve the finding.

The audit scans its entire installed environment, including its own tools (`pip-audit`, `pip-api`, `pypi-json`). A clean installation of the repository requirements contains colorama, jsonref, mando, mdurl and radon; the other six listed packages are absent. No audit tooling was added to the application requirements. This project has no Python lockfile to refresh.

## Validation

Installed Python dependencies in an isolated environment using `uv pip install --only-binary :all: -r requirements.txt -r requirements-dev.txt`. Installed frontend dependencies using `npm ci --ignore-scripts --no-audit --no-fund`. These installations did not change the dependency manifests or lockfile.

- Backend pytest: passed, 1,174 tests; five unawaited AsyncMock warnings.
- Backend Ruff lint: passed.
- Backend Ruff format check: passed, 400 files.
- Backend Pyright: passed, zero errors or warnings.
- Frontend tests: passed, 35 files and 250 tests; React act() and missing canvas implementation warnings.
- Frontend build (`tsc -b && vite build`): passed; large chunk warning.
- Frontend ESLint: passed, zero errors and two Fast Refresh warnings.
