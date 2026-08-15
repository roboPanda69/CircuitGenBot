"""Deterministic normalization of LLM draft output."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from schematic_ai.application.requirements.drafts import (
    RequirementChangeDraft,
    RequirementExtractionDraft,
)
from schematic_ai.domain.requirements.units import UnitNormalizationError, normalize_unit


class RequirementDraftNormalizationError(ValueError):
    """Raised when a validated draft cannot be normalized deterministically."""


class RequirementDraftNormalizer:
    def normalize_extraction(self, draft: RequirementExtractionDraft) -> RequirementExtractionDraft:
        data = draft.model_dump(mode="json")
        for requirement in data["requirements"]:
            requirement["constraint"] = self._normalize_constraint(requirement["constraint"])
            requirement["conditions"] = [
                {
                    **condition,
                    "constraint": self._normalize_constraint(condition["constraint"]),
                }
                for condition in requirement.get("conditions", [])
            ]
        for assumption in data["assumptions"]:
            assumption["value"] = self._normalize_assumption_value(assumption["value"])
        return self._validate_normalized(RequirementExtractionDraft, data)

    def normalize_change(self, draft: RequirementChangeDraft) -> RequirementChangeDraft:
        data = draft.model_dump(mode="json")
        for operation in data["operations"]:
            if operation["operation"] == "add_requirement":
                requirement = operation["requirement"]
                requirement["constraint"] = self._normalize_constraint(requirement["constraint"])
                requirement["conditions"] = [
                    {
                        **condition,
                        "constraint": self._normalize_constraint(condition["constraint"]),
                    }
                    for condition in requirement.get("conditions", [])
                ]
            elif operation["operation"] == "replace_requirement_constraint":
                operation["new_constraint"] = self._normalize_constraint(operation["new_constraint"])
        return self._validate_normalized(RequirementChangeDraft, data)

    def _normalize_constraint(self, constraint: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(constraint)
        try:
            if "unit" in normalized:
                normalized["unit"] = normalize_unit(normalized["unit"])
            if normalized.get("kind") == "nominal_with_tolerance":
                tolerance = normalized.get("tolerance", {})
                if tolerance.get("unit") is not None:
                    tolerance["unit"] = normalize_unit(tolerance["unit"])
        except UnitNormalizationError as exc:
            raise RequirementDraftNormalizationError(str(exc)) from exc
        return normalized

    def _normalize_assumption_value(self, value: Any) -> Any:
        if isinstance(value, dict) and "unit" in value:
            normalized = dict(value)
            try:
                normalized["unit"] = normalize_unit(normalized["unit"])
            except UnitNormalizationError as exc:
                raise RequirementDraftNormalizationError(str(exc)) from exc
            return normalized
        return value

    @staticmethod
    def _validate_normalized(model_type, data):
        try:
            return model_type.model_validate(data)
        except ValidationError as exc:
            raise RequirementDraftNormalizationError(str(exc)) from exc

