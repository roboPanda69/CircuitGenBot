"""LLM-facing requirement draft contracts.

These models are intentionally smaller than the canonical RequirementModel.
They are validated LLM output, not canonical engineering state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schematic_ai.domain.requirements.constraints import Condition, Constraint, Quantity
from schematic_ai.domain.requirements.enums import RequirementCategory, TargetType
from schematic_ai.domain.requirements.validation import require_identifier, require_nonblank


class DraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MessageEnvelope(DraftModel):
    message_id: str
    text: str
    project_id: str
    timestamp: datetime | None = None
    conversation_id: str | None = None

    @field_validator("message_id", "project_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "message id")

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "message text")

    @field_validator("conversation_id")
    @classmethod
    def optional_conversation_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "conversation_id")


class DraftRequirement(DraftModel):
    category: RequirementCategory
    type: str
    constraint: Constraint
    description: str | None = None
    target_type: TargetType | None = None
    target_id: str | None = None
    conditions: list[Condition] = Field(default_factory=list)
    priority: Literal["required", "recommended", "optional", "preference"] | None = None
    enforcement: Literal["hard", "soft", "advisory"] | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def type_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "requirement type")

    @field_validator("description", "target_id")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "draft text")


class DraftAssumption(DraftModel):
    description: str
    parameter: str
    value: Quantity | bool | str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    impact: Literal["low", "medium", "high", "critical"] = "medium"
    requires_confirmation: bool = False
    related_requirement_types: list[str] = Field(default_factory=list)

    @field_validator("description", "parameter")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "assumption text")


class DraftOpenQuestion(DraftModel):
    question: str
    reason: str
    blocking: bool
    importance: Literal["low", "medium", "high", "critical"] = "high"
    suggested_answers: list[str] = Field(default_factory=list)
    related_requirement_types: list[str] = Field(default_factory=list)

    @field_validator("question", "reason")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "question text")


class RequirementExtractionDraft(DraftModel):
    system_name: str | None = None
    system_description: str | None = None
    requirements: list[DraftRequirement] = Field(default_factory=list)
    assumptions: list[DraftAssumption] = Field(default_factory=list)
    open_questions: list[DraftOpenQuestion] = Field(default_factory=list)


class AddRequirementOperation(DraftModel):
    operation: Literal["add_requirement"]
    requirement: DraftRequirement


class ReplaceRequirementConstraintOperation(DraftModel):
    operation: Literal["replace_requirement_constraint"]
    target_requirement_id: str
    new_constraint: Constraint
    description: str | None = None

    @field_validator("target_requirement_id")
    @classmethod
    def target_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "target_requirement_id")


class RemoveRequirementOperation(DraftModel):
    operation: Literal["remove_requirement"]
    target_requirement_id: str
    reason: str | None = None

    @field_validator("target_requirement_id")
    @classmethod
    def target_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "target_requirement_id")


class AskOpenQuestionOperation(DraftModel):
    operation: Literal["ask_open_question"]
    question: DraftOpenQuestion


ChangeOperation = Annotated[
    AddRequirementOperation
    | ReplaceRequirementConstraintOperation
    | RemoveRequirementOperation
    | AskOpenQuestionOperation,
    Field(discriminator="operation"),
]


class RequirementChangeDraft(DraftModel):
    operations: list[ChangeOperation] = Field(min_length=1)
