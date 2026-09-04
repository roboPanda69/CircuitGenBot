"""Typed EDA artifact generation contracts for Milestone 8."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schematic_ai.domain.requirements.validation import reject_duplicates, require_identifier, require_nonblank


EDA_BACKEND_VERSION = "0.1"


class EDAModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, arbitrary_types_allowed=True)


class GenerationStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class GeneratedArtifactType(StrEnum):
    KICAD_SCHEMATIC = "kicad_schematic"
    PYTHON_CIRCUIT_REPRESENTATION = "python_circuit_representation"
    SKIDL_SOURCE = "skidl_source"
    MANIFEST = "manifest"
    DIAGNOSTIC_REPORT = "diagnostic_report"


class GeneratedArtifactFormat(StrEnum):
    KICAD_SCH = "kicad_sch"
    PYTHON = "python"
    JSON = "json"


class GenerationDiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class GenerationDiagnosticCategory(StrEnum):
    UNRESOLVED_COMPONENT = "unresolved_component"
    MISSING_SYMBOL = "missing_symbol"
    UNSUPPORTED_SYMBOL_VARIANT = "unsupported_symbol_variant"
    MISSING_FOOTPRINT = "missing_footprint"
    UNRESOLVED_PIN_MAPPING = "unresolved_pin_mapping"
    PLACEHOLDER_GENERATED = "placeholder_generated"
    UNSUPPORTED_FEATURE = "unsupported_feature"
    BACKEND_FAILURE = "backend_failure"
    INVALID_CIRCUIT = "invalid_circuit"
    ARTIFACT_CHECK_FAILED = "artifact_check_failed"
    OTHER = "other"


class BackendCapabilities(EDAModel):
    backend: str
    backend_version: str = EDA_BACKEND_VERSION
    target_version: str | None = None
    supports_schematic: bool
    supports_footprints: bool
    supports_placeholders: bool
    supports_partial_circuit: bool
    deterministic_generation: bool
    supports_round_trip: bool = False
    supported_formats: list[str] = Field(default_factory=list)

    @field_validator("backend")
    @classmethod
    def backend_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "backend")

    @field_validator("supported_formats")
    @classmethod
    def formats_must_be_unique(cls, value: list[str]) -> list[str]:
        return reject_duplicates([require_nonblank(item, "supported format") for item in value], "supported formats")

    @property
    def schematic_generation(self) -> bool:
        return self.supports_schematic

    @property
    def footprint_support(self) -> bool:
        return self.supports_footprints

    @property
    def placeholder_support(self) -> bool:
        return self.supports_placeholders

    @property
    def partial_circuit_support(self) -> bool:
        return self.supports_partial_circuit

    @property
    def round_trip_support(self) -> bool:
        return self.supports_round_trip


class GenerationContext(EDAModel):
    output_dir: Path
    artifact_basename: str = "circuit"
    allow_placeholders: bool = True
    include_python_representation: bool = False
    include_skidl: bool = Field(default=False, description="Deprecated compatibility alias for include_python_representation; does not generate real SKiDL constructs.")
    kicad_symbol_dir: Path | None = None
    write_manifest: bool = True
    write_diagnostic_report: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact_basename")
    @classmethod
    def artifact_basename_must_be_simple(cls, value: str) -> str:
        value = require_nonblank(value, "artifact basename")
        if any(char in value for char in "\\/:*?\"<>|"):
            raise ValueError("artifact_basename must be a simple file stem")
        return value


class GeneratedFile(EDAModel):
    artifact_type: GeneratedArtifactType
    path: str
    format: GeneratedArtifactFormat
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def path_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "generated file path")


class ObjectMapping(EDAModel):
    source_object_id: str
    source_object_type: str
    backend_object_id: str
    backend_object_type: str
    artifact_type: GeneratedArtifactType
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_object_id")
    @classmethod
    def source_object_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "source object id")

    @field_validator("source_object_type", "backend_object_id", "backend_object_type")
    @classmethod
    def mapping_text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "object mapping text")


class PlaceholderRecord(EDAModel):
    placeholder_object_id: str
    source_instance_id: str
    backend_object_id: str
    reference_designator: str
    display_value: str
    unresolved_reason: str
    pin_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_instance_id")
    @classmethod
    def source_instance_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "source instance id")

    @field_validator("placeholder_object_id", "backend_object_id", "reference_designator", "display_value", "unresolved_reason")
    @classmethod
    def placeholder_text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "placeholder text")

    @field_validator("pin_ids")
    @classmethod
    def pin_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        return reject_duplicates([require_identifier(item, "placeholder pin id") for item in value], "placeholder pin IDs")


class GenerationDiagnostic(EDAModel):
    diagnostic_id: str
    severity: GenerationDiagnosticSeverity
    category: GenerationDiagnosticCategory
    message: str
    source_object_id: str | None = None
    backend_object_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("diagnostic_id")
    @classmethod
    def diagnostic_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "diagnostic id")

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "diagnostic message")

    @field_validator("source_object_id")
    @classmethod
    def optional_source_object_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "diagnostic source object id")

    @field_validator("backend_object_id")
    @classmethod
    def optional_backend_object_id_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "diagnostic backend object id")


class GeneratedPinEndpoint(EDAModel):
    circuit_instance_id: str
    circuit_pin_id: str
    symbol_uuid: str
    kicad_pin_number: str
    position: dict[str, float]
    orientation: float
    connection_point: dict[str, float]

    @field_validator("circuit_instance_id", "circuit_pin_id")
    @classmethod
    def endpoint_ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "pin endpoint id")

    @field_validator("symbol_uuid", "kicad_pin_number")
    @classmethod
    def endpoint_text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "pin endpoint text")


class ArtifactCheckResult(EDAModel):
    valid: bool
    component_mismatches: list[str] = Field(default_factory=list)
    net_mismatches: list[str] = Field(default_factory=list)
    no_connect_mismatches: list[str] = Field(default_factory=list)
    refdes_mismatches: list[str] = Field(default_factory=list)
    value_mismatches: list[str] = Field(default_factory=list)
    placeholder_mismatches: list[str] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)
    diagnostics: list[GenerationDiagnostic] = Field(default_factory=list)
    generated_connectivity: dict[str, list[str]] = Field(default_factory=dict)
    expected_connectivity: dict[str, list[str]] = Field(default_factory=dict)
    generated_no_connects: list[str] = Field(default_factory=list)
    expected_no_connects: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_requires_no_mismatches(self) -> "ArtifactCheckResult":
        mismatches = (
            self.component_mismatches
            + self.net_mismatches
            + self.no_connect_mismatches
            + self.refdes_mismatches
            + self.value_mismatches
            + self.placeholder_mismatches
            + self.parse_errors
        )
        if self.valid and mismatches:
            raise ValueError("valid artifact check cannot include mismatches or parse errors")
        return self


class GeneratedArtifactManifest(EDAModel):
    manifest_id: str
    source_circuit_id: str
    source_circuit_revision: int = Field(ge=1)
    backend: str
    backend_version: str = EDA_BACKEND_VERSION
    generated_files: list[GeneratedFile] = Field(default_factory=list)
    object_mappings: list[ObjectMapping] = Field(default_factory=list)
    placeholders: list[PlaceholderRecord] = Field(default_factory=list)
    unresolved_objects: list[str] = Field(default_factory=list)
    warnings: list[GenerationDiagnostic] = Field(default_factory=list)
    errors: list[GenerationDiagnostic] = Field(default_factory=list)
    generation_status: GenerationStatus
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("manifest_id", "source_circuit_id")
    @classmethod
    def manifest_ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "manifest id")

    @field_validator("backend")
    @classmethod
    def backend_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "backend")

    @field_validator("unresolved_objects")
    @classmethod
    def unresolved_objects_must_be_unique(cls, value: list[str]) -> list[str]:
        return reject_duplicates([require_identifier(item, "unresolved object id") for item in value], "unresolved objects")


class GenerationResult(EDAModel):
    status: GenerationStatus
    backend: str
    capabilities: BackendCapabilities
    manifest: GeneratedArtifactManifest
    generated_files: list[GeneratedFile] = Field(default_factory=list)
    diagnostics: list[GenerationDiagnostic] = Field(default_factory=list)

    @field_validator("backend")
    @classmethod
    def backend_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "backend")

    @model_validator(mode="after")
    def status_must_match_diagnostics_and_artifacts(self) -> "GenerationResult":
        errors = [diag for diag in self.diagnostics if diag.severity == GenerationDiagnosticSeverity.ERROR]
        if self.status == GenerationStatus.SUCCESS:
            if errors:
                raise ValueError("successful generation cannot include error diagnostics")
            if self.manifest.placeholders or self.manifest.unresolved_objects:
                raise ValueError("successful generation cannot include placeholders or unresolved objects")
        if self.status == GenerationStatus.PARTIAL and errors:
            raise ValueError("partial generation cannot include blocking error diagnostics")
        if self.manifest.generation_status != self.status:
            raise ValueError("manifest generation_status must match result status")
        return self
