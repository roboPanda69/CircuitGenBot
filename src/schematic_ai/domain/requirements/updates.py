"""Controlled non-mutating updates for canonical RequirementModel instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from schematic_ai.domain.requirements.models import (
    Assumption,
    OpenQuestion,
    Requirement,
    RequirementModel,
)
from schematic_ai.domain.requirements.validation import require_identifier


class RequirementPatchError(ValueError):
    """Raised when a patch operation cannot be applied by stable ID."""


RequirementInput = Requirement | Mapping[str, Any]
AssumptionInput = Assumption | Mapping[str, Any]
OpenQuestionInput = OpenQuestion | Mapping[str, Any]


@dataclass(frozen=True)
class RequirementPatch:
    add_requirements: tuple[RequirementInput, ...] = field(default_factory=tuple)
    replace_requirements: tuple[RequirementInput, ...] = field(default_factory=tuple)
    remove_requirement_ids: tuple[str, ...] = field(default_factory=tuple)
    add_assumptions: tuple[AssumptionInput, ...] = field(default_factory=tuple)
    remove_assumption_ids: tuple[str, ...] = field(default_factory=tuple)
    update_open_questions: tuple[OpenQuestionInput, ...] = field(default_factory=tuple)

    @property
    def has_changes(self) -> bool:
        return any(
            (
                self.add_requirements,
                self.replace_requirements,
                self.remove_requirement_ids,
                self.add_assumptions,
                self.remove_assumption_ids,
                self.update_open_questions,
            )
        )


class RequirementUpdateService:
    """Apply minimal controlled patches through full model validation."""

    def apply_patch(
        self,
        current_model: RequirementModel,
        patch: RequirementPatch,
        *,
        updated_at: datetime | None = None,
        increment_revision: bool = True,
    ) -> RequirementModel:
        data = current_model.model_dump(mode="json")

        self._remove_by_id(data["requirements"], patch.remove_requirement_ids, "requirement")
        self._replace_by_id(data["requirements"], patch.replace_requirements, "requirement")
        data["requirements"].extend(self._dump_items(patch.add_requirements))

        self._remove_by_id(data["assumptions"], patch.remove_assumption_ids, "assumption")
        data["assumptions"].extend(self._dump_items(patch.add_assumptions))

        self._replace_by_id(data["open_questions"], patch.update_open_questions, "open question")

        if patch.has_changes:
            if increment_revision:
                data["revision"] += 1
            update_timestamp = updated_at or datetime.now(timezone.utc)
            if update_timestamp.tzinfo is None or update_timestamp.tzinfo.utcoffset(update_timestamp) is None:
                raise RequirementPatchError("updated_at must be timezone-aware")
            data["metadata"]["updated_at"] = update_timestamp.isoformat()

        return RequirementModel.model_validate(data)

    @staticmethod
    def _dump_items(items: tuple[RequirementInput, ...] | tuple[AssumptionInput, ...]) -> list[dict[str, Any]]:
        dumped: list[dict[str, Any]] = []
        for item in items:
            if hasattr(item, "model_dump"):
                dumped.append(item.model_dump(mode="json"))  # type: ignore[union-attr]
            else:
                dumped.append(dict(item))
        return dumped

    @staticmethod
    def _remove_by_id(items: list[dict[str, Any]], item_ids: tuple[str, ...], label: str) -> None:
        for item_id in item_ids:
            stable_id = require_identifier(item_id, f"{label} id")
            index = RequirementUpdateService._find_index(items, stable_id)
            if index is None:
                raise RequirementPatchError(f"cannot remove unknown {label} {stable_id}")
            del items[index]

    @staticmethod
    def _replace_by_id(
        items: list[dict[str, Any]],
        replacements: tuple[RequirementInput, ...] | tuple[OpenQuestionInput, ...],
        label: str,
    ) -> None:
        for replacement in RequirementUpdateService._dump_items(replacements):
            stable_id = require_identifier(str(replacement.get("id", "")), f"{label} id")
            index = RequirementUpdateService._find_index(items, stable_id)
            if index is None:
                raise RequirementPatchError(f"cannot replace unknown {label} {stable_id}")
            items[index] = replacement

    @staticmethod
    def _find_index(items: list[dict[str, Any]], item_id: str) -> int | None:
        for index, item in enumerate(items):
            if item.get("id") == item_id:
                return index
        return None
