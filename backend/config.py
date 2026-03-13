# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://agentickode:agentickode@postgres:5432/agentickode"

    # Ollama
    ollama_url: str = "http://localhost:11434"

    # OpenHands
    openhands_url: str = "http://localhost:3000"

    # ChromaDB
    chromadb_url: str = "http://localhost:8000"
    chromadb_token: str = ""

    # Gitea
    gitea_url: str = "https://gitea.yourdomain.com"
    gitea_token: str = ""

    # GitHub
    github_token: str = ""
    github_api_url: str = "https://api.github.com"

    # Bitbucket (workspace/repo access token from Bitbucket settings)
    bitbucket_access_token: str = ""
    bitbucket_base_url: str = "https://api.bitbucket.org"

    # GitLab
    gitlab_token: str = ""
    gitlab_api_url: str = "https://gitlab.com"

    # Workspace
    workspace_root: str = "/workspaces"
    default_ssh_key_path: str = "/app/.ssh/id_ed25519"
    sandbox_templates_path: str = "/opt/agentickode/docker/sandboxes"

    # Encryption
    encryption_key: str = ""

    # App
    app_base_url: str = "http://localhost:5173"

    # Worker
    max_concurrent_runs: int = 3
    poll_interval_seconds: int = 2
    approval_timeout_hours: int = 24
    phase_delay_seconds: int = 10

    # LLM Models
    planner_model: str = "qwen2.5-coder:32b-instruct-q4_K_M"
    coder_model: str = "devstral:24b-q5_K_M"
    reviewer_model: str = "qwen2.5-coder:14b-instruct-q5_K_M"
    fast_model: str = "qwen3:30b-a3b"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Cost per 1M tokens (input, output) in USD
MODEL_COST_RATES: dict[str, tuple[float, float]] = {
    "claude": (3.0, 15.0),
    "codex": (2.0, 8.0),
    "aider": (3.0, 15.0),
    "gemini": (1.25, 5.0),
    "kimi": (0.5, 2.0),
    "copilot": (0.0, 0.0),
    "ollama": (0.0, 0.0),
}
DEFAULT_COST_RATE: tuple[float, float] = (3.0, 15.0)
