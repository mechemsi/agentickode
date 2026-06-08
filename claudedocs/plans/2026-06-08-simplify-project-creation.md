---
title: Simplify project creation — paste git URL + name, hide the rest
status: planned
date: 2026-06-08
related:
  - frontend/src/components/shared/ProjectForm.tsx
  - frontend/src/pages/Projects.tsx
  - frontend/src/api/projects.ts
  - frontend/src/types/projects.ts
  - backend/api/projects.py
---

## Goal

Reduce the add-project form to two required fields (git URL + slug) and collapse all other fields under an optional "Advanced" disclosure, while keeping the issue-polling block permanently visible.

---

## Scope

### In scope
- Restructure `ProjectForm.tsx` into a minimal section + optional "Advanced" collapsible section
- Promote `project_slug` (read-only display of the autopopulated value, still editable if needed) as the only other required field
- Keep the issue-polling block (`poll_enabled` / `poll_interval_minutes`) always visible when `task_source` supports polling
- Move all remaining fields into the collapsible "Advanced" section:
  - Workspace server list + Test Connection button
  - `project_id`, `repo_owner`, `repo_name`, `default_branch`
  - `git_provider`, `task_source`
  - `git_provider_token`
  - `local_path`, `worker_user_override`
  - Notion integration fields (still gated on `task_source === "notion"` inside Advanced)
- Change Save validation: allow saving without an explicit Parse if the URL field is non-empty (let backend validate); hard-require Parse only when workspace server list is non-empty (to ensure branch resolution)
- Edit mode: no behaviour change — all fields already visible (user intentionally opened Edit)

### Out of scope
- Backend API changes — the `parse-git-url` endpoint and `createProject` / `updateProject` payloads remain untouched
- Changing which fields are stored or required by the backend
- Changes to `Projects.tsx` project list display
- Any changes to the edit-mode layout

---

## Technical Approach

### Files to modify

| File | Change |
|------|--------|
| `frontend/src/components/shared/ProjectForm.tsx` | All layout changes — see breakdown below |

No other files need to change.

### Field grouping

#### Always visible (create mode)
| Field | Notes |
|-------|-------|
| Git Repository URL + Parse button | Existing `UrlSection` component, unchanged |
| `project_slug` (display + editable) | Autopopulated by `handleParsed`; shown as "Project name" with a friendly label |
| Issue polling block | Already conditionally rendered on `POLL_CAPABLE_SOURCES`; keep as-is |

#### Hidden by default behind `<details>`/`<summary>` or a `showAdvanced` state toggle
| Field | Current location |
|-------|-----------------|
| Workspace server checklist + Test Connection | Lines 195–228 (create), 361–395 (edit) |
| `project_id` | Line 233 |
| `repo_owner` | Line 239 |
| `repo_name` | Line 243 |
| `default_branch` | Line 245 |
| `git_provider` | Line 248 |
| `task_source` | Line 253 |
| `git_provider_token` | Line 258 |
| `local_path` | Line 261 |
| `worker_user_override` | Line 270 |
| Notion fields block | Lines 280–327 (stays gated on `task_source === "notion"` inside Advanced) |

### Implementation detail

1. **Add `showAdvanced` state** (`useState(false)`) in `ProjectForm`.
2. **Wrap the advanced block** in a `<div>` rendered only when `showAdvanced === true`, preceded by a toggle button:
   ```tsx
   <button
     onClick={() => setShowAdvanced(v => !v)}
     className="..."
   >
     {showAdvanced ? "Hide advanced" : "Advanced options"}
   </button>
   ```
3. **`project_slug` stays outside the advanced block** — label it "Project name / slug" and show it directly below the URL row so users can see/override the autopopulated value.
4. **Polling block** stays outside the advanced block — already rendered conditionally on `POLL_CAPABLE_SOURCES`; no change needed.
5. **Edit mode**: `isEdit` already controls layout branching (lines 194, 230, 360, etc.). In edit mode, default `showAdvanced` to `true` (all fields should be immediately accessible when editing).

### Save validation change (lines 158–160)

Current guard:
```ts
if (!isEdit && !parsed && form.task_source !== "notion") {
  setSaveErr("Parse git URL first");
  return;
}
```

Proposed change:
- If `form.workspace_server_ids.length > 0`: keep the existing guard (branch resolution requires Parse).
- If no workspace server is selected: allow save without Parse, validating only that `gitUrl` is non-empty. This covers the common case where no workspace server is configured yet.

### Autopopulation flow — unchanged

`handleParsed` (line 140) already sets `project_id`, `project_slug`, `repo_owner`, `repo_name`, `default_branch`, `git_provider`, `task_source`. After parse, the slug is immediately visible in the minimal section; the rest land in Advanced.

---

## UX Detail

| Field | Visible by default (create) | Visible by default (edit) | Required |
|-------|----------------------------|--------------------------|----------|
| Git URL | Yes | No (read-only info already in project list) | Yes |
| `project_slug` | Yes (autopopulated, editable) | Yes | Yes |
| Polling block | Yes (if task_source is poll-capable) | Yes | No |
| Workspace servers | No (Advanced) | Yes (Advanced, pre-expanded) | No |
| `project_id` | No (Advanced) | Yes (Advanced, pre-expanded) | — |
| `repo_owner` / `repo_name` | No (Advanced) | Yes | — |
| `default_branch` | No (Advanced) | Yes | — |
| `git_provider` | No (Advanced) | Yes | — |
| `task_source` | No (Advanced) | Yes | — |
| `git_provider_token` | No (Advanced) | Yes | No |
| `local_path` | No (Advanced) | Yes | No |
| `worker_user_override` | No (Advanced) | Yes | No |
| Notion fields | No (Advanced, only if task_source=notion) | Yes (only if notion) | Conditional |

---

## Success Criteria

- [ ] Create-project form shows only URL input + project slug + Save/Cancel on initial render
- [ ] Parsing the URL autopopulates the slug field visibly (no page change needed)
- [ ] Clicking "Advanced options" reveals all other fields
- [ ] Issue-polling block is always visible (not inside Advanced) when task source supports it
- [ ] Edit mode opens with all fields visible (Advanced pre-expanded or no Advanced toggle)
- [ ] Saving a project without a workspace server selected works without being forced to Parse first (when git URL is non-empty)
- [ ] Saving with a workspace server selected still requires Parse (branch must be resolved)
- [ ] All existing `data-testid` attributes preserved (no test breakage)
- [ ] Notion block still only appears inside Advanced when `task_source === "notion"`
- [ ] No backend changes needed; payload shape is unchanged

---

## Risks / Open Questions

| Risk / Question | Notes |
|----------------|-------|
| Users may miss task_source defaulting to "plain" | After Parse, task_source is set automatically to the provider (github/gitea/gitlab) or "plain". This is now inside Advanced — the polling block will appear/disappear accordingly, which acts as a hint. |
| Polling block visibility trigger | Polling block still depends on `form.task_source`. After parse this is set correctly. If user never parses and task_source stays "plain", polling block stays hidden — acceptable since polling requires a provider. |
| `project_id` vs `project_slug` distinction | Both are autopopulated to the same slug value. Consider showing only `project_slug` in the minimal section and moving `project_id` entirely to Advanced (it is disabled in edit mode already). |
| Advanced pre-expanded in edit mode | Simplest implementation: `useState(isEdit)` — Advanced starts open when editing. Alternatively, keep it collapsed in edit mode too and let users expand as needed. Open question for the implementer. |
| Test coverage | `frontend/src/__tests__/` may have tests for `ProjectForm` — check for any assertions on fields now moved to Advanced. The `data-testid` attributes on `local-path-input` and `worker-user-override-input` must remain. |
