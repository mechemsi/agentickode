# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Ollama LLM service — class-based replacement for ollama.py."""

from dataclasses import dataclass

import httpx

from backend.config import settings


@dataclass(frozen=True)
class OllamaResult:
    """Structured result from an Ollama API call with actual token counts."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    total_duration_ns: int


class OllamaService:
    """Client for the Ollama API."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = ""):
        self._client = client
        self._base_url = base_url or settings.ollama_url

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.3,
        num_predict: int = 2048,
    ) -> OllamaResult:
        """Call Ollama /api/generate and return structured result with token counts."""
        model = model or settings.planner_model
        resp = await self._client.post(
            f"{self._base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": num_predict},
            },
            timeout=180.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return OllamaResult(
            text=data.get("response", ""),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_duration_ns=data.get("total_duration", 0),
        )

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.3,
        num_predict: int = 2048,
    ) -> OllamaResult:
        """Call Ollama /api/chat with separate system and user messages."""
        model = model or settings.planner_model
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await self._client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": num_predict},
            },
            timeout=180.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return OllamaResult(
            text=data.get("message", {}).get("content", ""),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_duration_ns=data.get("total_duration", 0),
        )

    async def is_healthy(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False