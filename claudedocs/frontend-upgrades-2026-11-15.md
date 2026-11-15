---
title: Frontend major dependency upgrades
status: implemented
date: 2026-11-15
related: [dependency-audit-2026-11-14.md]
---

# Frontend dependency upgrades

The checkout already contains most requested major upgrades and the associated
React/Tailwind source migrations. Preserve resolved ESLint 10.15.0 and Lucide
1.73.0, which exceed the requested 10.14.0 and 1.72.0. Do not downgrade them.

## Changes

| Package | Checkout | Result |
| --- | --- | --- |
| @types/react | declared ^19.2.18, locked 19.3.0 | minimum ^19.3.0 |
| @types/react-dom | declared ^19.2.4, locked 19.3.0 | minimum ^19.3.0 |
| @vitejs/plugin-react | declared ^6.0.5, locked 6.3.0 | minimum ^6.3.0 |
| vite | declared ^8.2.1, locked 8.3.8 | minimum ^8.3.8 |
| eslint | declared ^10.8.1, locked 10.15.0 | minimum ^10.14.0 |
| tailwindcss | 4.3.3 | 4.3.5 |
| @tailwindcss/postcss | 4.3.3 | 4.3.5, matches Tailwind |
| jsdom | 30.1.3 | 31.0.1 |
| vitest and @vitest/coverage-v8 | 4.1.12 | 5.1.0 together |
| TypeScript compiler | 6.0.3 | 7.0.2 through @typescript/native alias |

jest-dom 7.0.1, React/React DOM 19.3.1, React Router DOM 7.18.5,
React Hooks ESLint plugin 7.1.1, and marked 18.2.0 were already installed.

TypeScript 7 has no JavaScript compiler API. The current typescript-eslint
8.72.2 packages require TypeScript <6.1 and explicitly reject TypeScript 7.
Use Microsoft's [documented side-by-side installation](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/#running-side-by-side-with-typescript-6.0):
`@typescript/native` aliases `typescript@7.0.2`, supplying `tsc`; `typescript`
aliases `@typescript/typescript6@6.0.2`, supplying the API for linting and `tsc6`.
This additional compatibility package is required to keep existing checks working.
No peer checks or lint rules were disabled. The existing `tsc -b` build and CI
commands now use compiler 7.0.2 without script changes.

## Migration review

- React and both type packages: [React 19 upgrade guide](https://react.dev/blog/2024/04/25/react-19-upgrade-guide)
  covers the removed legacy APIs, JSX namespace and ref changes. `main.tsx`
  already uses createRoot and the automatic JSX transform; refs are initialized,
  including the previous Toast migration. No further edits needed.
- Router: [v6 to v7 guide](https://reactrouter.com/7.9.6/upgrading/v6).
  `main.tsx` uses declarative routes without multi-segment splats or data-router
  loaders/actions. Existing Link, useNavigate and useParams calls remain supported.
- [jest-dom 7 release](https://github.com/testing-library/jest-dom/releases/tag/v7.0.0):
  requires Node 22 and the DOM testing library peer, already installed through
  React Testing Library. `src/test-setup.ts` uses the Vitest matcher entry point.
- [React plugin changelog, majors 5 and 6](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/CHANGELOG.md):
  newer Node/Vite requirements and removed Babel features. Both Vite configs use
  plain react() without Babel customization.
- Vite [7 migration](https://v7.vite.dev/guide/migration) and
  [8 migration](https://vite.dev/guide/migration.html): Node minimum, browser
  targets and Rolldown/Oxc replacement. No custom Rollup/esbuild transforms,
  SSR integration or Sass legacy configuration to migrate.
- [ESLint 10 migration](https://eslint.org/docs/latest/use/migrate-to-10.0.0) and
  [Hooks plugin changelog, majors 6 and 7](https://github.com/react/react/blob/main/packages/eslint-plugin-react-hooks/CHANGELOG.md):
  existing flat config and explicit @eslint/js dependency are compatible. Keep
  the recommended Hooks rules enabled.
- jsdom releases [26](https://github.com/jsdom/jsdom/releases/tag/26.0.0),
  [27](https://github.com/jsdom/jsdom/releases/tag/27.0.0),
  [28](https://github.com/jsdom/jsdom/releases/tag/28.0.0),
  [29](https://github.com/jsdom/jsdom/releases/tag/29.0.0),
  [30](https://github.com/jsdom/jsdom/releases/tag/v30.0.0), and
  [31](https://github.com/jsdom/jsdom/releases/tag/v31.0.0): Node requirements,
  pointer events, resource loading, CSS/selector changes, asynchronous parsing
  and optional canvas backend changes. The actual remaining jump is 30 to 31.
  Tests use the Vitest environment, without custom JSDOM resource loading or
  native canvas integration. All tests pass with the new CSS implementation.
- [Lucide 1 release](https://github.com/lucide-icons/lucide/releases/tag/1.0.0):
  existing named icon imports already build with 1.73.0.
- [marked 18 release](https://github.com/markedjs/marked/releases/tag/v18.0.0):
  trailing token blank lines changed; sanitize.ts parses Markdown and sanitizes
  HTML without consuming raw block tokens. Existing sanitize tests pass.
- [Tailwind 4 upgrade guide](https://tailwindcss.com/docs/upgrade-guide):
  index.css and postcss.config.js already use the new plugin, CSS import and
  explicit JS config, with utility/default-style migrations from the prior audit.
  Update the plugin alongside Tailwind for 4.3.5.
- TypeScript [6 release/migration notes](https://devblogs.microsoft.com/typescript/announcing-typescript-6-0/)
  and [7 release/migration notes](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/):
  existing bundler resolution, ES2020 target, strict mode and explicit imports
  remain valid. The compiler API removal requires the aliases above.
- Vitest and V8 coverage: [5 migration guide](https://main.vitest.dev/guide/migration/)
  and [release notes](https://github.com/vitest-dev/vitest/releases/tag/v5.0.0).
  Reviewed mock-history clearing, top-level hoisted mocks, awaited async
  assertions, matcher types, removed entry points and coverage glob matching.
  Existing tests and root-relative coverage globs need no changes. Upgrade
  the runner and provider together because their versions must match.

## Validation

Commands run in frontend/ on Node 22.23.5, npm 10.9.9, without Docker:

- Baseline: npm ci --ignore-scripts, build, lint and tests passed (250 tests).
- Incremental installs used npm install --ignore-scripts; production builds
  passed after each upgrade group. jsdom and Vitest steps each passed 250 tests.
- Final clean npm ci --ignore-scripts: passed.
- npm ls --all: passed, including valid TypeScript compatibility peers.
- tsc --version: 7.0.2; tsc -b --force and npm run build: passed.
- npm run lint: passed with the same two KVEditor Fast Refresh warnings.
- npm run test:coverage: 35 test files, 250 tests passed with the V8 provider.

The production build retains its existing large-chunk warning. jsdom retains
unimplemented canvas warnings, now naming its new optional backend.
Docker builds, live backend services, browser visual checks and the full CI
suite were not verified here. CI selects Node 24; frontend Dockerfiles select Node 26.


## Requested-version revalidation

The follow-up request targets ESLint 10.15.0 and Lucide 1.73.0. At the
start of this pass, every requested version was already resolved, including
TypeScript 7.0.2 through the documented native compiler alias. Raised the
ESLint declaration from ^10.14.0 to ^10.15.0 using
`npm install --ignore-scripts`; package-lock.json now records the same minimum.
No resolved package versions changed and no further source migrations were needed.
The TypeScript 6 API alias remains necessary for typescript-eslint 8.72.2.

Re-read the linked upstream major migration notes and changelogs, including
jsdom 26 through 31, React plugin 5 and 6, Hooks plugin 6 and 7, Vite 7 and 8,
and TypeScript 6 and 7. Checked package imports, React refs and root rendering,
router declarations, Markdown sanitization, test setup and mocks, Tailwind
utilities/configuration, and ESLint presets against the existing migrations.

Fresh validation on Node 22.23.5 and npm 10.9.9:

- `npm install --ignore-scripts` and `npm ci --ignore-scripts`: passed.
- `npm ls --all`: passed; `tsc --version` reports 7.0.2.
- `npm run build`: typecheck and production build passed.
- `npm run lint`: passed, with the two existing KVEditor Fast Refresh warnings.
- `npm test` and `npm run test:coverage`: each passed all 250 tests in 35 files.

Existing large-bundle and unimplemented jsdom canvas warnings remain.
Docker, backend services, browser visual checks and the full CI suite are
untested in this pass.
