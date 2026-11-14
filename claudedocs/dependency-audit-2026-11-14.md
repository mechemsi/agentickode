---
title: Dependency audit updates
status: implemented
date: 2026-11-14
related: []
---

# Dependency audit updates

Updated the remaining packages from the supplied audit. Packages already above its target versions were preserved. Install scripts were disabled for npm; Python packages were installed from wheels only.

## Frontend resolved versions

| Package | Before | After |
|---------|--------|-------|
| @eslint/js | 9.39.2 | 10.0.1 |
| @tailwindcss/postcss | added | 4.3.3 |
| @testing-library/jest-dom | 6.9.1 | 7.0.1 |
| @types/react | 18.3.28 | 19.3.0 |
| @types/react-dom | 18.3.7 | 19.3.0 |
| @vitejs/plugin-react | 4.7.0 | 6.3.0 |
| @vitest/coverage-v8 | 4.1.0 | 4.1.12 |
| dompurify | 3.4.17 | 3.4.18 |
| eslint | 9.39.2 | 10.15.0 |
| eslint-plugin-react-hooks | 5.2.0 | 7.1.1 |
| jsdom | 25.0.1 | 30.1.3 |
| lucide-react | 0.574.0 | 1.73.0 |
| marked | 17.0.3 | 18.2.0 |
| react | 18.3.1 | 19.3.1 |
| react-dom | 18.3.1 | 19.3.1 |
| tailwindcss | 3.4.19 | 4.3.3 |
| typescript | 5.9.3 | 6.0.3 |
| vite | 6.4.6 | 8.3.8 |
| vitest | 4.1.0 | 4.1.12 |

Added the explicit @eslint/js dependency because ESLint 10 no longer supplies the package imported by eslint.config.js. Added @tailwindcss/postcss for Tailwind 4 and a scoped minimatch override (^11.0.1) for typescript-estree to address GHSA-g3hv-75wg-m249. Vitest and its coverage provider were updated together to 4.1.12 to clear their current advisories.

## Backend

| Package | Before | After |
|---------|--------|-------|
| aiosqlite | 0.20.0 | 0.22.1 |
| pytest | 9.0.3 | 9.1.1 |
| pytest-asyncio | 1.3.0 | 1.4.0 |
| pytest-cov | 6.0.0 | 7.1.0 |
| ruff | 0.8.4 | 0.16.3 |
| pyright | 1.1.390 | 1.1.411 |
| FastMCP minimum | 3.0.0 | 4.0.0 |
| Pydantic minimum | 2.10.3 | 2.14.0 |

The parent minimums require MCP 2 and pydantic-core newer than 2.48.0. The fresh validation environment resolved FastMCP 4.2.0, MCP 2.3.0, Pydantic 2.14.3, and pydantic-core 2.50.4. This project uses requirements files without a Python lockfile.

## Compatibility edits

- React 19: initialize the toast timeout ref explicitly.
- Tailwind 4: use its PostCSS plugin, import CSS and explicitly load the existing JS configuration. Replace removed/renamed utilities and preserve border, placeholder, and button cursor defaults, following the [official migration guide](https://tailwindcss.com/docs/upgrade-guide).
- New Ruff rules: mark unused unpacked values, use StrEnum, make test regex patterns raw, and apply the updated formatter.
- New Pyright: type the sort-column mapping and use its stored fallback column; return the explicit unreachable result while a server is setting up.

## Remaining constraints

- mando stays at 0.7.1: the latest Radon 6.0.1 requires mando >=0.6,<0.8. There is no compatible parent release permitting 0.8.2.
- TypeScript moves to 6.0.3. TypeScript 7.0.2 is blocked by the latest @typescript-eslint/parser 8.72.2, whose peer range is >=4.8.4 <6.1.0. No forced or invalid peer installation was used.

## Validation

- Backend pytest: 1,167 passed; five existing AsyncMock runtime warnings.
- Backend Ruff lint and format check: passed (399 files).
- Backend Pyright with the validation environment selected: zero errors or warnings.
- MCP smoke check: server imported and SSE app constructed successfully.
- Frontend coverage tests: 35 files, 250 tests passed. jsdom reports unimplemented canvas methods.
- Frontend build (tsc -b and Vite): passed; bundle-size warning remains.
- Frontend ESLint: 28 errors and two warnings. New React Hooks recommended rules flag existing synchronous effect updates (26 errors) and declaration order (two errors). These checks remain enabled; broader component restructuring is outside this dependency update.
- npm audit: zero vulnerabilities.
- Clean npm ci --ignore-scripts: passed after refreshing optional dependency entries in the lockfile.
