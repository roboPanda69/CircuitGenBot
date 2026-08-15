"""Ollama LLM backend."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from schematic_ai.config import load_settings
from schematic_ai.llm.client import LLMClientError


@dataclass(frozen=True)
class OllamaClient:
    model: str | None = None
    host: str | None = None
    timeout_seconds: float = 60.0

    def generate_structured(
        self,
        *,
        prompt: str,
        json_schema: dict | None = None,
    ) -> str:
        settings = load_settings()
        model = self.model or settings.ollama_model
        host = (self.host or settings.ollama_host).rstrip("/")
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if json_schema is not None:
            payload["format"] = json_schema

        request = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMClientError(f"Ollama request failed: {exc}") from exc

        try:
            return str(body["response"])
        except KeyError as exc:
            raise LLMClientError("Ollama response did not contain a response field") from exc

