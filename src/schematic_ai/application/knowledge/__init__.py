"""Engineering Knowledge Foundation v0.1 application services."""

from schematic_ai.application.knowledge.adapters import KnowledgeDraft, KnowledgeSourceAdapter
from schematic_ai.application.knowledge.kicad import (
    KiCadFootprintEntry,
    KiCadSymbolEntry,
    footprint_reference_if_exists,
    index_kicad_footprints,
    index_kicad_symbols,
    kicad_library_source,
    symbol_reference_if_exists,
)
from schematic_ai.application.knowledge.repository import (
    InMemoryKnowledgeRepository,
    KnowledgeRepositoryError,
)

__all__ = [
    "InMemoryKnowledgeRepository",
    "KiCadFootprintEntry",
    "KiCadSymbolEntry",
    "KnowledgeDraft",
    "KnowledgeRepositoryError",
    "KnowledgeSourceAdapter",
    "footprint_reference_if_exists",
    "index_kicad_footprints",
    "index_kicad_symbols",
    "kicad_library_source",
    "symbol_reference_if_exists",
]
