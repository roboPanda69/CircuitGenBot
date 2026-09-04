"""EDA backend exceptions surfaced as typed generation diagnostics."""

from __future__ import annotations


class BackendGenerationError(RuntimeError):
    """Raised when an EDA backend cannot produce a trustworthy artifact."""


class SymbolResolutionError(BackendGenerationError):
    """Raised when a component symbol cannot be resolved safely."""


class PinMappingError(BackendGenerationError):
    """Raised when CircuitIR pins cannot be mapped to backend pins safely."""


class UnsupportedCircuitObjectError(BackendGenerationError):
    """Raised when a CircuitIR object cannot be represented by the backend."""


class ArtifactWriteError(BackendGenerationError):
    """Raised when generated artifacts cannot be written."""
