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
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "qwen-coder")


@dataclass(frozen=True)
class AppSettings:
    kicad9_footprint_dir: str | None = KICAD9_FOOTPRINT_DIR
    kicad9_symbol_dir: str | None = KICAD9_SYMBOL_DIR
    llm_provider: str = LLM_PROVIDER
    ollama_model_name: str = OLLAMA_MODEL_NAME


def load_settings() -> AppSettings:
    return AppSettings(
        kicad9_footprint_dir=os.getenv("KICAD9_FOOTPRINT_DIR"),
        kicad9_symbol_dir=os.getenv("KICAD9_SYMBOL_DIR"),
        llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
        ollama_model_name=os.getenv("OLLAMA_MODEL_NAME", "qwen-coder"),
    )

