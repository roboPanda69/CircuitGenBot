"""RequirementModel v0.1 typed domain contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schematic_ai.domain.requirements.constraints import Condition, Constraint, Quantity
from schematic_ai.domain.requirements.enums import (
    AssumptionSource,
    ConflictResolutionStatus,
    ConflictSeverity,
    ConflictType,
    Enforcement,
    Impact,
    OriginType,
    QuestionImportance,
    QuestionStatus,
    RelationshipType,
    RequirementCategory,
    RequirementPriority,
    RequirementStatus,
    TargetType,
    VerificationMethod,
)
from schematic_ai.domain.requirements.validation import (
    reject_duplicates,
    require_identifier,
    require_nonblank,
)


SCHEMA_VERSION = "0.1"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SystemInfo(DomainModel):
    name: str
    description: str
    domain: str = "general_electronics"

    @field_validator("name", "description", "domain")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "system field")


class Target(DomainModel):
    type: TargetType
    id: str | None = None

    @field_validator("id")
    @classmethod
    def optional_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "target id")


class Origin(DomainModel):
    type: OriginType
    source_id: str | None = None
    note: str | None = None

    @field_validator("source_id")
    @classmethod
    def optional_source_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "source_id")

    @field_validator("note")
    @classmethod
    def optional_note_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "note")


class Relationship(DomainModel):
    type: RelationshipType
    requirement_id: str

    @field_validator("requirement_id")
    @classmethod
    def requirement_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "requirement_id")


class VerificationAcceptance(DomainModel):
    all_required_methods_must_pass: bool = False


class VerificationExpectation(DomainModel):
    required: bool = True
    preferred_methods: list[VerificationMethod] = Field(default_factory=list)
    acceptance: VerificationAcceptance = Field(default_factory=VerificationAcceptance)


class Requirement(DomainModel):
    id: str
    category: RequirementCategory
    type: str
    description: str
    target: Target
    constraint: Constraint
    conditions: list[Condition] = Field(default_factory=list)
    priority: RequirementPriority
    enforcement: Enforcement
    origin: Origin
    status: RequirementStatus
    confidence: float = Field(ge=0.0, le=1.0)
    dependencies: list[Relationship] = Field(default_factory=list)
    group_id: str | None = None
    verification: VerificationExpectation = Field(default_factory=VerificationExpectation)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "id")

    @field_validator("type", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "requirement text")

    @field_validator("group_id")
    @classmethod
    def optional_group_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "group_id")

    @field_validator("tags")
    @classmethod
    def tags_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return [require_nonblank(tag, "tag") for tag in value]


class DerivedRequirement(Requirement):
    derived_from: list[str] = Field(min_length=1)
    rule_id: str
    status: Literal[RequirementStatus.DERIVED] = RequirementStatus.DERIVED

    @field_validator("derived_from")
    @classmethod
    def derived_from_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(requirement_id, "derived_from") for requirement_id in value]
        return reject_duplicates(ids, "derived_from")

    @field_validator("rule_id")
    @classmethod
    def rule_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "rule_id")


class Assumption(DomainModel):
    id: str
    description: str
    parameter: str
    value: Quantity | bool | str
    source: AssumptionSource
    confidence: float = Field(ge=0.0, le=1.0)
    impact: Impact
    requires_confirmation: bool = False
    affects_requirements: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "id")

    @field_validator("description", "parameter")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "assumption text")

    @field_validator("value")
    @classmethod
    def string_value_must_not_be_blank(cls, value: Quantity | bool | str) -> Quantity | bool | str:
        if isinstance(value, str):
            return require_nonblank(value, "assumption value")
        return value

    @field_validator("affects_requirements")
    @classmethod
    def affected_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        return [require_identifier(requirement_id, "affects_requirements") for requirement_id in value]


class OpenQuestion(DomainModel):
    id: str
    question: str
    reason: str
    related_requirement_ids: list[str] = Field(default_factory=list)
    importance: QuestionImportance
    blocking: bool
    suggested_answers: list[str] = Field(default_factory=list)
    status: QuestionStatus = QuestionStatus.OPEN

    @field_validator("id")
    @classmethod
    def id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "id")

    @field_validator("question", "reason")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "question text")

    @field_validator("related_requirement_ids")
    @classmethod
    def related_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        return [require_identifier(requirement_id, "related_requirement_ids") for requirement_id in value]

    @field_validator("suggested_answers")
    @classmethod
    def suggested_answers_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return [require_nonblank(answer, "suggested answer") for answer in value]


class Conflict(DomainModel):
    id: str
    requirement_ids: list[str] = Field(min_length=2)
    type: ConflictType
    description: str
    severity: ConflictSeverity
    resolution_status: ConflictResolutionStatus = ConflictResolutionStatus.UNRESOLVED

    @field_validator("id")
    @classmethod
    def id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "id")

    @field_validator("requirement_ids")
    @classmethod
    def requirement_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(requirement_id, "requirement_ids") for requirement_id in value]
        return reject_duplicates(ids, "requirement_ids")

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "description")


class Metadata(DomainModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str

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
    def updated_at_must_not_precede_created_at(self) -> "Metadata":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be greater than or equal to created_at")
        return self


class RequirementModel(DomainModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    requirement_set_id: str
    project_id: str
    revision: int = Field(ge=1)
    system: SystemInfo
    requirements: list[Requirement] = Field(default_factory=list)
    derived_requirements: list[DerivedRequirement] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    metadata: Metadata

    @field_validator("requirement_set_id", "project_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "model id")

    @model_validator(mode="after")
    def validate_internal_references(self) -> "RequirementModel":
        explicit_ids = [requirement.id for requirement in self.requirements]
        derived_ids = [requirement.id for requirement in self.derived_requirements]
        all_ids = explicit_ids + derived_ids

        duplicates = sorted({requirement_id for requirement_id in all_ids if all_ids.count(requirement_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate requirement ids: {', '.join(duplicates)}")

        self._validate_unique_namespace("assumption ids", [assumption.id for assumption in self.assumptions])
        self._validate_unique_namespace("open question ids", [question.id for question in self.open_questions])
        self._validate_unique_namespace("conflict ids", [conflict.id for conflict in self.conflicts])

        known_ids = set(all_ids)
        for requirement in [*self.requirements, *self.derived_requirements]:
            for dependency in requirement.dependencies:
                if dependency.requirement_id == requirement.id:
                    raise ValueError(f"{requirement.id} cannot depend on itself")
                if dependency.requirement_id not in known_ids:
                    raise ValueError(
                        f"{requirement.id} references unknown dependency {dependency.requirement_id}"
                    )

        for derived in self.derived_requirements:
            for source_id in derived.derived_from:
                if source_id not in known_ids:
                    raise ValueError(f"{derived.id} derived from unknown requirement {source_id}")

        for assumption in self.assumptions:
            for requirement_id in assumption.affects_requirements:
                if requirement_id not in known_ids:
                    raise ValueError(
                        f"{assumption.id} affects unknown requirement {requirement_id}"
                    )

        for question in self.open_questions:
            for requirement_id in question.related_requirement_ids:
                if requirement_id not in known_ids:
                    raise ValueError(
                        f"{question.id} relates to unknown requirement {requirement_id}"
                    )

        for conflict in self.conflicts:
            for requirement_id in conflict.requirement_ids:
                if requirement_id not in known_ids:
                    raise ValueError(
                        f"{conflict.id} references unknown requirement {requirement_id}"
                    )

        return self

    @staticmethod
    def _validate_unique_namespace(namespace: str, ids: list[str]) -> None:
        duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate {namespace}: {', '.join(duplicates)}")
