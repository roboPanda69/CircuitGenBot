"""EDA Backend v0.1 application layer."""

from schematic_ai.application.eda.backend import EDABackend
from schematic_ai.application.eda.checker import KiCadArtifactChecker
from schematic_ai.application.eda.errors import (
    ArtifactWriteError,
    BackendGenerationError,
    PinMappingError,
    SymbolResolutionError,
    UnsupportedCircuitObjectError,
)
from schematic_ai.application.eda.kicad import KiCadBackend
from schematic_ai.application.eda.layout import (
    ComponentPlacement,
    NetLabelPlacement,
    Point,
    SchematicLayout,
    SchematicLayoutStrategy,
)
from schematic_ai.application.eda.models import (
    ArtifactCheckResult,
    BackendCapabilities,
    GeneratedArtifactFormat,
    GeneratedArtifactManifest,
    GeneratedArtifactType,
    GeneratedFile,
    GeneratedPinEndpoint,
    GenerationContext,
    GenerationDiagnostic,
    GenerationDiagnosticCategory,
    GenerationDiagnosticSeverity,
    GenerationResult,
    GenerationStatus,
    ObjectMapping,
    PlaceholderRecord,
)
from schematic_ai.application.eda.resolvers import (
    FootprintResolution,
    FootprintResolver,
    PinMappingResolution,
    PinMappingResolver,
    SymbolResolution,
    SymbolResolver,
)
from schematic_ai.application.eda.skidl import PythonCircuitRepresentationBackend, SKiDLBackend

__all__ = [
    "ArtifactCheckResult",
    "ArtifactWriteError",
    "BackendCapabilities",
    "BackendGenerationError",
    "ComponentPlacement",
    "EDABackend",
    "FootprintResolution",
    "FootprintResolver",
    "GeneratedArtifactFormat",
    "GeneratedArtifactManifest",
    "GeneratedArtifactType",
    "GeneratedFile",
    "GeneratedPinEndpoint",
    "GenerationContext",
    "GenerationDiagnostic",
    "GenerationDiagnosticCategory",
    "GenerationDiagnosticSeverity",
    "GenerationResult",
    "GenerationStatus",
    "KiCadBackend",
    "KiCadArtifactChecker",
    "NetLabelPlacement",
    "ObjectMapping",
    "PinMappingError",
    "PinMappingResolution",
    "PinMappingResolver",
    "PlaceholderRecord",
    "Point",
    "PythonCircuitRepresentationBackend",
    "SKiDLBackend",
    "SchematicLayout",
    "SchematicLayoutStrategy",
    "SymbolResolution",
    "SymbolResolutionError",
    "SymbolResolver",
    "UnsupportedCircuitObjectError",
]
