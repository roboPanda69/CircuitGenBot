"""Replaceable EDA backend abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from hashlib import sha256
from pathlib import Path

from schematic_ai.application.eda.models import BackendCapabilities, GenerationContext, GenerationResult
from schematic_ai.domain.circuit_ir import CircuitIR


class EDABackend(ABC):
    """One-way translation boundary from canonical CircuitIR to EDA artifacts."""

    name: str
    backend_version = "0.1"

    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        """Return typed backend capability metadata."""

    @abstractmethod
    def generate(self, circuit_ir: CircuitIR, context: GenerationContext) -> GenerationResult:
        """Generate derived artifacts without mutating CircuitIR."""


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def relative_artifact_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve().relative_to(output_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()
