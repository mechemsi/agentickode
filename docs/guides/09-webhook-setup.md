# Chapter 9: Webhook Setup

This guide explains how to manually configure webhooks so that issues (and optionally pull requests) from your git provider trigger AutoDev task runs.

## Prerequisites

1. A running AutoDev instance reachable from the internet (or your git provider's network)
2. A project already created in AutoDev with the correct `git_provider` and `repo_owner`/`repo_name`
3. Admin access to the repository in your git provider

## How It Works

When an issue is created or labeled with **`ai-task`**, the git provider sends a webhook payload to AutoDev. AutoDev matches the repo to a project config, creates a `task_run`, and the worker pipeline picks it up.

Adding the **`use-claude`** label alongside `ai-task` tells AutoDev to use the Claude API instead of the default coding agent.

## Endpoint Reference

| Endpoint | Provider | Trigger |
|---|---|---|
| `POST /api/webhooks/github` | GitHub | Issue created/labeled with `ai-task` |
| `POST /api/webhooks/gitlab` | GitLab | Issue opened/updated with `ai-task` label |
| `POST /api/webhooks/gitea` | Gitea | Issue created/labeled with `ai-task` |
| `POST /api/webhooks/plane` | Plane | Issue event with `ai-task` label |
| `POST /api/webhooks/github-pr` | GitHub | PR opened/synchronized (auto-review) |
| `POST /api/webhooks/gitea-pr` | Gitea | PR opened/synchronized (auto-review) |

---

## GitHub

### Step 1: Create the `ai-task` label

1. Go to your repository on GitHub
2. Navigate to **Issues** > **Labels**
3. Click **New label**
4. Name: `ai-task`, pick a color, click **Create label**
5. (Optional) Create a `use-claude` label if you want the Claude API option

### Step 2: Add the issue webhook

1. Go to **Settings** > **Webhooks** > **Add webhook**
2. Configure:
   - **Payload URL**: `https://<your-autodev-host>/api/webhooks/github`
   - **Content type**: `application/json`
   - **Secret**: leave blank (or configure if you add signature verification later)
   - **Which events?**: Select **Let me select individual events**, then check **Issues**
   - Click **Add webhook**

### Step 3 (Optional): Add the PR review webhook

To enable automatic PR reviews:

1. Add another webhook with:
   - **Payload URL**: `https://<your-autodev-host>/api/webhooks/github-pr`
   - **Content type**: `application/json`
   - **Events**: Select **Pull requests**
   - Click **Add webhook**

### Usage

1. Create an issue in your repository
2. Add the `ai-task` label to the issue
3. AutoDev will pick it up and start the worker pipeline

---

## GitLab

### Step 1: Create the `ai-task` label

1. Go to your project on GitLab
2. Navigate to **Manage** > **Labels**
3. Click **New label**
4. Title: `ai-task`, pick a color, click **Create label**
5. (Optional) Create a `use-claude` label

### Step 2: Add the webhook

1. Go to **Settings** > **Webhooks**
2. Click **Add new webhook**
3. Configure:
   - **URL**: `https://<your-autodev-host>/api/webhooks/gitlab`
   - **Secret token**: leave blank
   - **Trigger**: Check **Issues events**
   - Click **Add webhook**

### Usage

1. Create an issue in your GitLab project
2. Add the `ai-task` label
3. AutoDev receives the webhook when the issue is opened or updated with the label

> **Note**: GitLab uses `object_kind: "issue"` and `labels[].title` (not `name`). AutoDev handles this automatically.

---

## Gitea

### Step 1: Create the `ai-task` label

1. Go to your repository on Gitea
2. Navigate to **Issues** > **Labels**
3. Click **Create Label**
4. Name: `ai-task`, pick a color, click **Create Label**
5. (Optional) Create a `use-claude` label

### Step 2: Add the issue webhook

1. Go to **Settings** > **Webhooks** > **Add Webhook** > **Gitea**
2. Configure:
   - **Target URL**: `https://<your-autodev-host>/api/webhooks/gitea`
   - **HTTP Method**: POST
   - **Content type**: `application/json`
   - **Secret**: leave blank
   - **Trigger On**: Select **Custom Events**, then check **Issues**
   - Click **Add Webhook**

### Step 3 (Optional): Add the PR review webhook

1. Add another webhook with:
   - **Target URL**: `https://<your-autodev-host>/api/webhooks/gitea-pr`
   - **Trigger On**: Custom Events > **Pull Request**
   - Click **Add Webhook**

### Usage

1. Create an issue in your Gitea repository
2. Add the `ai-task` label
3. AutoDev picks it up automatically

---

## Plane

### Step 1: Create the `ai-task` label

1. Go to your Plane workspace
2. Navigate to **Settings** > **Labels**
3. Create a label named `ai-task`
4. (Optional) Create a `use-claude` label

### Step 2: Configure the webhook

1. Go to **Settings** > **Webhooks**
2. Click **Create webhook**
3. Configure:
   - **URL**: `https://<your-autodev-host>/api/webhooks/plane`
   - **Events**: Select issue events
4. Save the webhook

### Usage

1. Create an issue in Plane
2. Add the `ai-task` label
3. AutoDev matches the issue's `project` ID to the `project_id` in your AutoDev project config

> **Important**: For Plane, the `project_id` in your AutoDev project config must match the Plane project UUID.

---

## Plain (API-Only) Task Source

Projects configured with `task_source: "plain"` do not use webhooks. Tasks are created directly via the AutoDev API:

```bash
POST /api/runs
{
  "task_id": "my-task-1",
  "project_id": "your-project-id",
  "title": "Implement feature X",
  "description": "Detailed description of what to build..."
}
```

---

## Troubleshooting

### Webhook not triggering

- Verify the webhook URL is reachable from your git provider's network
- Check the webhook delivery log in your provider's settings (GitHub/GitLab/Gitea all show recent deliveries)
- Ensure the `ai-task` label is spelled exactly right (case-sensitive)
- Confirm the issue event type is selected (not just push events)

### Issue ignored with `unknown_project`

- AutoDev matches by `git_provider` + `repo_owner` + `repo_name`
- Verify your project config has the correct values (check via `GET /api/projects`)
- For Plane, the `project_id` must match the Plane project UUID exactly

### Issue ignored with `not_ai_task`

- The issue must have the `ai-task` label applied
- For GitHub/Gitea: label must be in `issue.labels[].name`
- For GitLab: label must be in `labels[].title`
- For Plane: label must be in `data.labels[].name`
