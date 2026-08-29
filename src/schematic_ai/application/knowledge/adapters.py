"""Knowledge ingestion adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from schematic_ai.domain.knowledge import ComponentRecord, Evidence, KnowledgeSource


@dataclass(frozen=True)
class KnowledgeDraft:
    """Adapter output before deterministic repository validation."""

    sources: list[KnowledgeSource] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    components: list[ComponentRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class KnowledgeSourceAdapter(Protocol):
    """Boundary for future local structured, KiCad, or document adapters."""

    def load(self) -> KnowledgeDraft:
        """Return draft knowledge records for deterministic validation."""
