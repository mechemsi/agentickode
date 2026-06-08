---
title: Simplify project creation — minimal form + Advanced disclosure
status: implemented
date: 2026-06-08
related:
  - claudedocs/plans/2026-06-08-simplify-project-creation.md
  - frontend/src/components/shared/ProjectForm.tsx
---

# Simplify project creation

## What was built

The add-project form (`ProjectForm`) now opens minimal in create mode: only the
**git URL (paste + Parse)**, the **Project name / slug**, the **issue-polling block**
(when the source supports it), and an **"Advanced options"** toggle. Everything else
is autopopulated by Parse and tucked behind the toggle. Edit mode is unchanged —
it opens with all fields visible.

## Key files

| File | Change |
|------|--------|
| `frontend/src/components/shared/ProjectForm.tsx` | Added `showAdvanced` state (`useState(isEdit)`); extracted all non-essential fields into an `advancedFields` fragment rendered only when expanded; promoted `project_slug` (relabelled "Project name / slug") and kept the polling block always visible; added a `toggle-advanced` button (Chevron). Unified the previously-duplicated create/edit workspace-server blocks into one. |
| `frontend/src/__tests__/ProjectForm.test.tsx` | Replaced 2 create-mode tests that assumed advanced fields were visible; added 3 tests (minimal view hides advanced; expanding reveals them; edit shows them). 20 tests pass. |

## How it works

- `showAdvanced` defaults to `isEdit` → collapsed on create, expanded on edit.
- The minimal create view = `UrlSection` + `project_slug` + polling (conditional) + toggle + Save/Cancel.
- `handleParsed` autopopulation is unchanged; after Parse the slug is visible and the
  rest land in Advanced. Polling visibility still keys off `task_source`, which Parse sets.

## Notes / deviations

- **Save validation kept as-is** (Parse still required in create mode). The plan
  proposed relaxing it for the no-workspace-server case, but that would submit empty
  `repo_owner`/`repo_name` (the backend reads those directly), creating broken projects.
  A true URL-only create flow needs a backend change (parse the URL in `create_project`).
- No backend or payload changes. All `data-testid`s preserved.
- Open question deferred: whether Advanced should auto-expand in edit (currently yes).
