"""Structured engineering constraints for RequirementModel v0.1."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schematic_ai.domain.requirements.validation import (
    reject_duplicates,
    require_finite_number,
    require_nonblank,
)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Quantity(DomainModel):
    value: float
    unit: str

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, value: float) -> float:
        return require_finite_number(value, "value")

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "unit")


class Tolerance(DomainModel):
    type: Literal["percent", "absolute"]
    minus: float = Field(ge=0)
    plus: float = Field(ge=0)
    unit: str | None = None

    @field_validator("minus", "plus")
    @classmethod
    def tolerance_must_be_finite(cls, value: float) -> float:
        return require_finite_number(value, "tolerance")

    @field_validator("unit")
    @classmethod
    def optional_unit_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "unit")

    @model_validator(mode="after")
    def absolute_tolerance_requires_unit(self) -> "Tolerance":
        if self.type == "absolute" and self.unit is None:
            raise ValueError("absolute tolerance requires unit")
        return self


class ExactConstraint(DomainModel):
    kind: Literal["exact"] = "exact"
    value: float
    unit: str

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, value: float) -> float:
        return require_finite_number(value, "value")

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "unit")


class NominalConstraint(DomainModel):
    kind: Literal["nominal"] = "nominal"
    value: float
    unit: str

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, value: float) -> float:
        return require_finite_number(value, "value")

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "unit")


class MinimumConstraint(DomainModel):
    kind: Literal["minimum"] = "minimum"
    value: float
    unit: str

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, value: float) -> float:
        return require_finite_number(value, "value")

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "unit")


class MaximumConstraint(DomainModel):
    kind: Literal["maximum"] = "maximum"
    value: float
    unit: str

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, value: float) -> float:
        return require_finite_number(value, "value")

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "unit")


class RangeConstraint(DomainModel):
    kind: Literal["range"] = "range"
    minimum: float
    maximum: float
    unit: str

    @field_validator("minimum", "maximum")
    @classmethod
    def values_must_be_finite(cls, value: float) -> float:
        return require_finite_number(value, "range value")

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "unit")

    @model_validator(mode="after")
    def minimum_must_not_exceed_maximum(self) -> "RangeConstraint":
        if self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        return self


class BooleanConstraint(DomainModel):
    kind: Literal["boolean"] = "boolean"
    value: bool


class EnumConstraint(DomainModel):
    kind: Literal["enum"] = "enum"
    allowed: list[str] = Field(min_length=1)

    @field_validator("allowed")
    @classmethod
    def options_must_not_be_blank(cls, value: list[str]) -> list[str]:
        options = [require_nonblank(option, "allowed option") for option in value]
        return reject_duplicates(options, "allowed")


class EnumPreferenceConstraint(DomainModel):
    kind: Literal["enum_preference"] = "enum_preference"
    preferred: list[str] = Field(min_length=1)

    @field_validator("preferred")
    @classmethod
    def options_must_not_be_blank(cls, value: list[str]) -> list[str]:
        options = [require_nonblank(option, "preferred option") for option in value]
        return reject_duplicates(options, "preferred")


class TextConstraint(DomainModel):
    kind: Literal["text"] = "text"
    value: str

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "value")


class NominalWithToleranceConstraint(DomainModel):
    kind: Literal["nominal_with_tolerance"] = "nominal_with_tolerance"
    nominal: float
    unit: str
    tolerance: Tolerance

    @field_validator("nominal")
    @classmethod
    def nominal_must_be_finite(cls, value: float) -> float:
        return require_finite_number(value, "nominal")

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "unit")


Constraint = Annotated[
    Union[
        ExactConstraint,
        NominalConstraint,
        MinimumConstraint,
        MaximumConstraint,
        RangeConstraint,
        BooleanConstraint,
        EnumConstraint,
        EnumPreferenceConstraint,
        TextConstraint,
        NominalWithToleranceConstraint,
    ],
    Field(discriminator="kind"),
]


class Condition(DomainModel):
    parameter: str
    constraint: Constraint

    @field_validator("parameter")
    @classmethod
    def parameter_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "parameter")
