"""Application-level settings for replaceable local backends.

These settings intentionally stay outside the domain model. They describe the
current local tool choices, not the RequirementModel contract.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


KICAD9_FOOTPRINT_DIR = os.getenv("KICAD9_FOOTPRINT_DIR")
KICAD9_SYMBOL_DIR = os.getenv("KICAD9_SYMBOL_DIR")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("OLLAMA_MODEL_NAME", "qwen-coder"))
OLLAMA_MODEL_NAME = OLLAMA_MODEL
LLM_MAX_REPAIR_ATTEMPTS = int(os.getenv("LLM_MAX_REPAIR_ATTEMPTS", "2"))


@dataclass(frozen=True)
class AppSettings:
    kicad9_footprint_dir: str | None = KICAD9_FOOTPRINT_DIR
    kicad9_symbol_dir: str | None = KICAD9_SYMBOL_DIR
    llm_provider: str = LLM_PROVIDER
    ollama_host: str = OLLAMA_HOST
    ollama_model: str = OLLAMA_MODEL
    ollama_model_name: str = OLLAMA_MODEL_NAME
    llm_max_repair_attempts: int = LLM_MAX_REPAIR_ATTEMPTS


def load_settings() -> AppSettings:
    ollama_model = os.getenv("OLLAMA_MODEL", os.getenv("OLLAMA_MODEL_NAME", "qwen-coder"))
    return AppSettings(
        kicad9_footprint_dir=os.getenv("KICAD9_FOOTPRINT_DIR"),
        kicad9_symbol_dir=os.getenv("KICAD9_SYMBOL_DIR"),
        llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=ollama_model,
        ollama_model_name=ollama_model,
        llm_max_repair_attempts=int(os.getenv("LLM_MAX_REPAIR_ATTEMPTS", "2")),
    )
