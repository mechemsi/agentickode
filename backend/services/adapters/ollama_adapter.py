# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""OllamaAdapter — wraps OllamaService for a specific model."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.ollama_service import OllamaService


class OllamaAdapter:
    """RoleAdapter implementation backed by an Ollama server."""

    def __init__(self, ollama_service: OllamaService, model_name: str, server_name: str = ""):
        self._service = ollama_service
        self._model = model_name
        self._server_name = server_name
        self._last_token_usage: tuple[int, int] | None = None

    @property
    def provider_name(self) -> str:
        label = f"ollama/{self._model}"
        if self._server_name:
            label += f"@{self._server_name}"
        return label

    @property
    def last_token_usage(self) -> tuple[int, int] | None:
        """Return (prompt_tokens, completion_tokens) from the last call, or None."""
        return self._last_token_usage

    async def generate(self, prompt: str, **kwargs: object) -> str:
        temperature = float(kwargs.get("temperature", 0.3))
        num_predict = int(kwargs.get("num_predict", 2048))
        system_prompt = kwargs.get("system_prompt")

        if system_prompt:
            result = await self._service.chat(
                system_prompt=str(system_prompt),
                user_prompt=prompt,
                model=self._model,
                temperature=temperature,
                num_predict=num_predict,
            )
        else:
            result = await self._service.generate(
                prompt,
                model=self._model,
                temperature=temperature,
                num_predict=num_predict,
            )

        self._last_token_usage = (result.prompt_tokens, result.completion_tokens)
        return result.text

    async def run_task(self, workspace: str, instruction: str, **kwargs: object) -> dict:
        raise NotImplementedError("Ollama cannot execute coding tasks directly")

    async def is_available(self) -> bool:
        return await self._service.is_healthy()