"""Circuit Planner v0.1 result contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schematic_ai.domain.circuit_ir import CircuitIR, ImplementationStatus
from schematic_ai.domain.requirements.validation import reject_duplicates, require_identifier, require_nonblank


class CircuitPlannerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CircuitPlanningStatus(StrEnum):
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    NEEDS_INPUT = "needs_input"
    FAILED = "failed"


class CircuitPlanningIssueType(StrEnum):
    KNOWLEDGE_MISSING = "knowledge_missing"
    NO_CANDIDATE = "no_candidate"
    CONSTRAINT_CONFLICT = "constraint_conflict"
    IMPLEMENTATION_AMBIGUITY = "implementation_ambiguity"
    INCOMPLETE_ARCHITECTURE = "incomplete_architecture"
    INVALID_DRAFT = "invalid_draft"
    OTHER = "other"


class CandidateEligibility(StrEnum):
    PREFERRED = "preferred"
    ELIGIBLE = "eligible"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class ValueBasisType(StrEnum):
    REQUIREMENT = "requirement"
    COMPONENT_ATTRIBUTE = "component_attribute"
    MANUFACTURER_REFERENCE = "manufacturer_reference"
    USER_FORCED = "user_forced"
    CALCULATION = "calculation"


class ValueResolutionBasis(CircuitPlannerModel):
    basis_type: ValueBasisType
    requirement_ids: list[str] = Field(default_factory=list)
    component_attribute_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    calculation_id: str | None = None
    forced_by_user: bool = False

    @field_validator("requirement_ids", "component_attribute_ids", "evidence_ids")
    @classmethod
    def refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "value basis reference") for item in value]
        return reject_duplicates(ids, "value basis references")

    @field_validator("calculation_id")
    @classmethod
    def optional_calculation_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "calculation_id")


class CircuitPlanningMetadata(CircuitPlannerModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "circuit_planner"

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("created_by")
    @classmethod
    def created_by_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "created_by")

    @model_validator(mode="after")
    def updated_at_must_not_precede_created_at(self) -> "CircuitPlanningMetadata":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be greater than or equal to created_at")
        return self


class CircuitPlanningIssue(CircuitPlannerModel):
    issue_id: str
    issue_type: CircuitPlanningIssueType
    target_ids: list[str] = Field(default_factory=list)
    description: str
    blocking: bool
    related_requirement_ids: list[str] = Field(default_factory=list)
    related_design_plan_ids: list[str] = Field(default_factory=list)
    metadata: CircuitPlanningMetadata = Field(default_factory=CircuitPlanningMetadata)

    @field_validator("issue_id")
    @classmethod
    def issue_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "issue_id")

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "issue description")

    @field_validator("target_ids", "related_requirement_ids", "related_design_plan_ids")
    @classmethod
    def refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "planning issue reference") for item in value]
        return reject_duplicates(ids, "planning issue references")


class ComponentCandidateEvaluation(CircuitPlannerModel):
    target_instance_ref: str
    component_record_id: str
    eligibility: CandidateEligibility
    satisfied_constraints: list[str] = Field(default_factory=list)
    preference_matches: list[str] = Field(default_factory=list)
    unresolved_constraints: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    value_resolution_bases: list[ValueResolutionBasis] = Field(default_factory=list)
    metadata: CircuitPlanningMetadata = Field(default_factory=CircuitPlanningMetadata)

    @field_validator("target_instance_ref", "component_record_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "candidate evaluation id")

    @field_validator("satisfied_constraints", "preference_matches", "unresolved_constraints", "rejection_reasons", "evidence_ids")
    @classmethod
    def list_text_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return reject_duplicates([require_nonblank(item, "candidate evaluation text") for item in value], "candidate evaluation values")


class CircuitPlanningResult(CircuitPlannerModel):
    status: CircuitPlanningStatus
    circuit_ir: CircuitIR | None = None
    issues: list[CircuitPlanningIssue] = Field(default_factory=list)
    candidate_evaluations: list[ComponentCandidateEvaluation] = Field(default_factory=list)
    metadata: CircuitPlanningMetadata = Field(default_factory=CircuitPlanningMetadata)
    diagnostics: dict[str, str | int | list[str]] = Field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.status == CircuitPlanningStatus.ACCEPTED and self.circuit_ir is not None

    @model_validator(mode="after")
    def status_fields_must_be_consistent(self) -> "CircuitPlanningResult":
        blocking_issues = [issue for issue in self.issues if issue.blocking]
        if self.status == CircuitPlanningStatus.ACCEPTED:
            if self.circuit_ir is None:
                raise ValueError("accepted circuit planning results require CircuitIR")
            if self.circuit_ir.implementation_status != ImplementationStatus.RESOLVED:
                raise ValueError("accepted circuit planning results require resolved CircuitIR implementation_status")
            if blocking_issues:
                raise ValueError("accepted circuit planning results cannot contain blocking issues")
        elif self.status == CircuitPlanningStatus.PARTIAL:
            if self.circuit_ir is None:
                raise ValueError("partial circuit planning results require CircuitIR")
            if self.circuit_ir.implementation_status == ImplementationStatus.RESOLVED:
                raise ValueError("partial circuit planning results require non-resolved CircuitIR implementation_status")
        elif self.status == CircuitPlanningStatus.NEEDS_INPUT:
            if not blocking_issues:
                raise ValueError("needs_input circuit planning results require at least one blocking issue")
        elif self.status == CircuitPlanningStatus.FAILED and self.circuit_ir is not None:
            raise ValueError("failed circuit planning results must not include CircuitIR")
        return self
