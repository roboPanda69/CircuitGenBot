"""Narrow deterministic KiCad library indexing for Milestone 5."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from schematic_ai.config import load_settings
from schematic_ai.domain.knowledge import (
    FootprintReference,
    KnowledgeMetadata,
    KnowledgeSource,
    SourceTrustClass,
    SymbolReference,
)


@dataclass(frozen=True)
class KiCadSymbolEntry:
    library: str
    symbol_name: str


@dataclass(frozen=True)
class KiCadFootprintEntry:
    library: str
    footprint_name: str


def index_kicad_symbols(symbol_dir: str | Path | None = None) -> list[KiCadSymbolEntry]:
    root = resolve_symbol_dir(symbol_dir)
    if root is None or not root.exists():
        return []
    entries: list[KiCadSymbolEntry] = []
    for library_file in sorted(root.glob("*.kicad_sym")):
        text = library_file.read_text(encoding="utf-8", errors="ignore")
        library = library_file.stem
        for symbol_name in re.findall(r'\(symbol\s+"([^"]+)"', text):
            if ":" in symbol_name:
                continue
            entries.append(KiCadSymbolEntry(library=library, symbol_name=symbol_name))
    return entries


def index_kicad_footprints(footprint_dir: str | Path | None = None) -> list[KiCadFootprintEntry]:
    root = resolve_footprint_dir(footprint_dir)
    if root is None or not root.exists():
        return []
    entries: list[KiCadFootprintEntry] = []
    for library_dir in sorted(root.glob("*.pretty")):
        if not library_dir.is_dir():
            continue
        library = library_dir.stem
        for footprint_file in sorted(library_dir.glob("*.kicad_mod")):
            entries.append(KiCadFootprintEntry(library=library, footprint_name=footprint_file.stem))
    return entries


def symbol_reference_if_exists(
    *,
    library: str,
    symbol_name: str,
    source_id: str,
    symbol_dir: str | Path | None = None,
) -> SymbolReference | None:
    entries = {(entry.library, entry.symbol_name) for entry in index_kicad_symbols(symbol_dir)}
    if (library, symbol_name) not in entries:
        return None
    return SymbolReference(
        library=library,
        symbol_name=symbol_name,
        source_id=source_id,
        verified_exists=True,
        metadata=KnowledgeMetadata(created_by="kicad_indexer"),
    )


def footprint_reference_if_exists(
    *,
    library: str,
    footprint_name: str,
    source_id: str,
    package_mapping: str | None = None,
    footprint_dir: str | Path | None = None,
) -> FootprintReference | None:
    entries = {(entry.library, entry.footprint_name) for entry in index_kicad_footprints(footprint_dir)}
    if (library, footprint_name) not in entries:
        return None
    return FootprintReference(
        library=library,
        footprint_name=footprint_name,
        package_mapping=package_mapping,
        source_id=source_id,
        verified_exists=True,
        metadata=KnowledgeMetadata(created_by="kicad_indexer"),
    )


def kicad_library_source(source_id: str, *, locator: str, title: str = "Local KiCad Library") -> KnowledgeSource:
    return KnowledgeSource(
        source_id=source_id,
        source_type="kicad_library",
        title=title,
        locator=locator,
        trust_class=SourceTrustClass.AUTHORITATIVE,
        metadata=KnowledgeMetadata(created_by="kicad_indexer"),
    )


def resolve_symbol_dir(symbol_dir: str | Path | None) -> Path | None:
    if symbol_dir is not None:
        return Path(symbol_dir)
    configured = load_settings().kicad9_symbol_dir
    return Path(configured) if configured else None


def resolve_footprint_dir(footprint_dir: str | Path | None) -> Path | None:
    if footprint_dir is not None:
        return Path(footprint_dir)
    configured = load_settings().kicad9_footprint_dir
    return Path(configured) if configured else None
