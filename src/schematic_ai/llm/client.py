"""LLM client protocol used by application services."""

from __future__ import annotations

from typing import Protocol


class LLMClientError(RuntimeError):
    """Raised when an LLM backend cannot complete a request."""


class LLMStructuredOutputError(LLMClientError):
    """Raised when a backend returns unusable structured output."""


class LLMClient(Protocol):
    def generate_structured(
        self,
        *,
        prompt: str,
        json_schema: dict | None = None,
    ) -> str:
        """Return structured JSON text for the supplied prompt."""

