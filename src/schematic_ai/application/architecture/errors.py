"""Architecture planner error types."""

from __future__ import annotations


class ArchitecturePlannerError(RuntimeError):
    """Base error for architecture planning failures."""


class ArchitectureDraftValidationError(ArchitecturePlannerError):
    """Raised when LLM draft output is invalid."""


class ArchitectureEnrichmentError(ArchitecturePlannerError):
    """Raised when a valid draft cannot be canonically enriched."""


class ArchitectureSemanticValidationError(ArchitecturePlannerError):
    """Raised when a DesignPlan contradicts explicit RequirementModel facts."""


class ArchitecturePlanningError(ArchitecturePlannerError):
    """Raised when planning cannot produce a valid result."""
