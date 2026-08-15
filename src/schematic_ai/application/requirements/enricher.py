"""Deterministic enrichment from validated drafts to canonical RequirementModel."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from schematic_ai.application.requirements.drafts import (
    DraftOpenQuestion,
    DraftRequirement,
    MessageEnvelope,
    RequirementChangeDraft,
    RequirementExtractionDraft,
)
from schematic_ai.domain.requirements.enums import VerificationMethod
from schematic_ai.domain.requirements.models import (
    Assumption,
    Metadata,
    OpenQuestion,
    Origin,
    Requirement,
    RequirementModel,
    SystemInfo,
    Target,
    VerificationAcceptance,
    VerificationExpectation,
)
from schematic_ai.domain.requirements.updates import RequirementPatch, RequirementUpdateService


_CATEGORY_PREFIX = {
    "power": "PWR",
    "functional": "FUNC",
    "interface": "IF",
    "protection": "PROT",
    "electrical": "ELEC",
    "performance": "PERF",
    "environmental": "ENV",
    "physical": "PHYS",
    "component": "COMP",
    "manufacturing": "MFG",
    "cost": "COST",
    "reliability": "REL",
    "safety": "SAFE",
    "user_preference": "PREF",
    "other": "GEN",
}


_VERIFICATION_METHODS = {
    "input_voltage": [VerificationMethod.DATASHEET_CONSTRAINT, VerificationMethod.ELECTRICAL_CALCULATION],
    "output_voltage": [VerificationMethod.DATASHEET_CONSTRAINT, VerificationMethod.SIMULATION],
    "output_current": [VerificationMethod.DATASHEET_CONSTRAINT, VerificationMethod.ELECTRICAL_CALCULATION],
    "power_consumption": [VerificationMethod.ELECTRICAL_CALCULATION],
    "reverse_polarity_protection": [VerificationMethod.CONNECTIVITY, VerificationMethod.ENGINEERING_RULE],
    "reverse_polarity": [VerificationMethod.CONNECTIVITY, VerificationMethod.ENGINEERING_RULE],
    "communication_interface": [VerificationMethod.CONNECTIVITY, VerificationMethod.DATASHEET_CONSTRAINT],
    "preferred_manufacturer": [VerificationMethod.DATASHEET_CONSTRAINT, VerificationMethod.MANUAL_REVIEW],
}


@dataclass
class RequirementEnricher:
    update_service: RequirementUpdateService | None = None

    def build_initial_model(
        self,
        *,
        message: MessageEnvelope,
        draft: RequirementExtractionDraft,
        created_at: datetime | None = None,
    ) -> RequirementModel:
        timestamp = created_at or datetime.now(timezone.utc)
        id_allocator = RequirementIdAllocator()
        requirements = [
            self._to_requirement(draft_requirement, message, id_allocator)
            for draft_requirement in draft.requirements
        ]
        assumptions = [
            self._to_assumption(assumption, index + 1, requirements)
            for index, assumption in enumerate(draft.assumptions)
        ]
        questions = [
            self._to_open_question(question, index + 1, requirements)
            for index, question in enumerate(draft.open_questions)
        ]
        questions.extend(self._missing_output_current_questions(requirements, len(questions)))
        if not requirements and not questions:
            questions.append(self._empty_extraction_question())

        model = RequirementModel(
            requirement_set_id="RQS_0001",
            project_id=message.project_id,
            revision=1,
            system=SystemInfo(
                name=draft.system_name or "Untitled Electronic System",
                description=draft.system_description or message.text,
                domain="general_electronics",
            ),
            requirements=requirements,
            derived_requirements=[],
            assumptions=assumptions,
            open_questions=questions,
            conflicts=[],
            metadata=Metadata(
                created_at=timestamp,
                updated_at=timestamp,
                created_by="requirement_interpreter",
            ),
        )
        return model

    def apply_change(
        self,
        *,
        message: MessageEnvelope,
        current_model: RequirementModel,
        draft: RequirementChangeDraft,
        updated_at: datetime | None = None,
    ) -> tuple[RequirementModel | None, list[OpenQuestion]]:
        update_service = self.update_service or RequirementUpdateService()
        id_allocator = RequirementIdAllocator.from_model(current_model)
        additions: list[Requirement] = []
        replacements: list[Requirement] = []
        removals: list[str] = []
        questions: list[OpenQuestion] = []

        for operation in draft.operations:
            if operation.operation == "add_requirement":
                additions.append(self._to_requirement(operation.requirement, message, id_allocator))
            elif operation.operation == "replace_requirement_constraint":
                existing = self._find_requirement(current_model, operation.target_requirement_id)
                data = existing.model_dump(mode="json")
                data["constraint"] = operation.new_constraint.model_dump(mode="json")
                if operation.description is not None:
                    data["description"] = operation.description
                data["origin"] = Origin(type="user", source_id=message.message_id).model_dump(mode="json")
                data["verification"] = self._verification_for_type(existing.type).model_dump(mode="json")
                replacements.append(Requirement.model_validate(data))
            elif operation.operation == "remove_requirement":
                removals.append(operation.target_requirement_id)
            elif operation.operation == "ask_open_question":
                questions.append(
                    self._to_open_question(
                        operation.question,
                        self._next_question_number(current_model, len(questions)),
                        list(current_model.requirements),
                    )
                )

        if not any((additions, replacements, removals)):
            if not questions:
                return None, []
            updated_model = update_service.apply_patch(
                current_model,
                RequirementPatch(add_open_questions=tuple(questions)),
                updated_at=updated_at,
            )
            return updated_model, questions

        updated_model = update_service.apply_patch(
            current_model,
            RequirementPatch(
                add_requirements=tuple(additions),
                replace_requirements=tuple(replacements),
                remove_requirement_ids=tuple(removals),
                add_open_questions=tuple(questions),
            ),
            updated_at=updated_at,
        )
        return updated_model, questions

    def _to_requirement(
        self,
        draft: DraftRequirement,
        message: MessageEnvelope,
        id_allocator: "RequirementIdAllocator",
    ) -> Requirement:
        requirement_id = id_allocator.next_requirement_id(str(draft.category))
        priority = draft.priority or self._default_priority(draft)
        enforcement = draft.enforcement or self._default_enforcement(draft)
        return Requirement(
            id=requirement_id,
            category=draft.category,
            type=draft.type,
            description=draft.description or self._default_description(draft),
            target=Target(
                type=draft.target_type or self._default_target_type(draft),
                id=draft.target_id or self._default_target_id(draft),
            ),
            constraint=draft.constraint,
            conditions=draft.conditions,
            priority=priority,
            enforcement=enforcement,
            origin=Origin(type="user", source_id=message.message_id),
            status="confirmed",
            confidence=1.0,
            dependencies=[],
            group_id=self._default_group_id(draft),
            verification=self._verification_for_type(draft.type),
            tags=draft.tags,
        )

    @staticmethod
    def _to_assumption(draft, index: int, requirements: list[Requirement]) -> Assumption:
        return Assumption(
            id=f"ASM_{index:03d}",
            description=draft.description,
            parameter=draft.parameter,
            value=draft.value,
            source="ai",
            confidence=draft.confidence,
            impact=draft.impact,
            requires_confirmation=draft.requires_confirmation,
            affects_requirements=[
                requirement.id
                for requirement in requirements
                if requirement.type in draft.related_requirement_types
            ],
        )

    @staticmethod
    def _to_open_question(draft: DraftOpenQuestion, index: int, requirements: list[Requirement]) -> OpenQuestion:
        return OpenQuestion(
            id=f"Q_{index:03d}",
            question=draft.question,
            reason=draft.reason,
            related_requirement_ids=[
                requirement.id
                for requirement in requirements
                if requirement.type in draft.related_requirement_types
            ],
            importance=draft.importance,
            blocking=draft.blocking,
            suggested_answers=draft.suggested_answers,
            status="open",
        )

    @staticmethod
    def _missing_output_current_questions(
        requirements: list[Requirement],
        existing_question_count: int,
    ) -> list[OpenQuestion]:
        has_output_voltage = any(requirement.type == "output_voltage" for requirement in requirements)
        has_output_current = any(requirement.type == "output_current" for requirement in requirements)
        if not has_output_voltage or has_output_current:
            return []
        related = [requirement.id for requirement in requirements if requirement.type == "output_voltage"]
        return [
            OpenQuestion(
                id=f"Q_{existing_question_count + 1:03d}",
                question="What output current is required?",
                reason="Output current is needed for regulator and power-stage selection.",
                related_requirement_ids=related,
                importance="high",
                blocking=True,
                suggested_answers=[],
                status="open",
            )
        ]

    @staticmethod
    def _empty_extraction_question() -> OpenQuestion:
        return OpenQuestion(
            id="Q_001",
            question=(
                "What should the circuit do? Please provide at least its main function, "
                "power requirements, or required interfaces."
            ),
            reason="No actionable engineering requirements were extracted from the message.",
            related_requirement_ids=[],
            importance="high",
            blocking=True,
            suggested_answers=[],
            status="open",
        )

    @staticmethod
    def _default_priority(draft: DraftRequirement) -> str:
        if str(draft.category) == "user_preference" or draft.type == "preferred_manufacturer":
            return "preference"
        return "required"

    @staticmethod
    def _default_enforcement(draft: DraftRequirement) -> str:
        if str(draft.category) == "user_preference" or draft.type == "preferred_manufacturer":
            return "soft"
        return "hard"

    @staticmethod
    def _default_description(draft: DraftRequirement) -> str:
        return f"{draft.type.replace('_', ' ')} requirement."

    @staticmethod
    def _default_target_type(draft: DraftRequirement) -> str:
        if draft.type == "input_voltage":
            return "power_input"
        if draft.type in {"output_voltage", "output_current"}:
            return "power_output"
        if draft.type in {"communication_interface", "interface_speed"}:
            return "interface"
        if draft.type in {"reverse_polarity", "reverse_polarity_protection"}:
            return "power_input"
        if draft.type == "preferred_manufacturer":
            return "component"
        return "system"

    @staticmethod
    def _default_target_id(draft: DraftRequirement) -> str | None:
        if draft.type == "input_voltage":
            return "VIN"
        if draft.type in {"output_voltage", "output_current"}:
            return "VOUT_MAIN"
        if draft.type in {"communication_interface", "interface_speed"}:
            return "INTERFACE_MAIN"
        if draft.type in {"reverse_polarity", "reverse_polarity_protection"}:
            return "VIN"
        if draft.type == "preferred_manufacturer":
            return "preferred_parts"
        return None

    @staticmethod
    def _default_group_id(draft: DraftRequirement) -> str | None:
        if draft.type == "input_voltage":
            return "REQGRP_PWR_IN_01"
        if draft.type in {"output_voltage", "output_current"}:
            return "REQGRP_PWR_OUT_01"
        return None

    @staticmethod
    def _verification_for_type(requirement_type: str) -> VerificationExpectation:
        methods = _VERIFICATION_METHODS.get(requirement_type, [VerificationMethod.NOT_YET_DEFINED])
        return VerificationExpectation(
            required=True,
            preferred_methods=methods,
            acceptance=VerificationAcceptance(all_required_methods_must_pass=False),
        )

    @staticmethod
    def _find_requirement(model: RequirementModel, requirement_id: str) -> Requirement:
        for requirement in model.requirements:
            if requirement.id == requirement_id:
                return requirement
        raise ValueError(f"unknown requirement {requirement_id}")

    @staticmethod
    def _next_question_number(model: RequirementModel, offset: int) -> int:
        existing = []
        for question in model.open_questions:
            match = re.match(r"^Q_(\d+)$", question.id)
            if match:
                existing.append(int(match.group(1)))
        return (max(existing) if existing else 0) + offset + 1


class RequirementIdAllocator:
    def __init__(self, existing_ids: Iterable[str] = ()):
        self._counters: dict[str, int] = {}
        for requirement_id in existing_ids:
            match = re.match(r"^REQ_([A-Z]+)_(\d+)$", requirement_id)
            if match:
                prefix, number = match.groups()
                self._counters[prefix] = max(self._counters.get(prefix, 0), int(number))

    @classmethod
    def from_model(cls, model: RequirementModel) -> "RequirementIdAllocator":
        return cls(requirement.id for requirement in [*model.requirements, *model.derived_requirements])

    def next_requirement_id(self, category: str) -> str:
        prefix = _CATEGORY_PREFIX.get(category, "GEN")
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"REQ_{prefix}_{self._counters[prefix]:03d}"
