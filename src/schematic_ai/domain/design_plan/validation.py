"""Contextual validation for DesignPlan and RequirementModel."""

from __future__ import annotations

from schematic_ai.domain.design_plan.enums import RequirementMappingStatus
from schematic_ai.domain.design_plan.models import DesignPlan
from schematic_ai.domain.requirements.enums import Enforcement, RequirementStatus
from schematic_ai.domain.requirements.models import RequirementModel


class DesignPlanContextValidationError(ValueError):
    """Raised when a DesignPlan is inconsistent with its source RequirementModel."""


def validate_design_plan_against_requirements(
    design_plan: DesignPlan,
    requirement_model: RequirementModel,
) -> None:
    if design_plan.source_requirement_set.requirement_set_id != requirement_model.requirement_set_id:
        raise DesignPlanContextValidationError("source requirement_set_id does not match RequirementModel")
    if design_plan.source_requirement_set.revision != requirement_model.revision:
        raise DesignPlanContextValidationError("source requirement revision does not match RequirementModel")

    all_requirements = [*requirement_model.requirements, *requirement_model.derived_requirements]
    known_requirement_ids = {requirement.id for requirement in all_requirements}

    mapped_or_dispositioned: set[str] = set()
    for mapping in design_plan.requirement_mappings:
        if mapping.requirement_id not in known_requirement_ids:
            raise DesignPlanContextValidationError(
                f"{mapping.mapping_id} references unknown requirement {mapping.requirement_id}"
            )
        if mapping.status in {
            RequirementMappingStatus.MAPPED,
            RequirementMappingStatus.PARTIALLY_MAPPED,
            RequirementMappingStatus.UNRESOLVED,
            RequirementMappingStatus.NOT_APPLICABLE,
        }:
            mapped_or_dispositioned.add(mapping.requirement_id)

    for decision in design_plan.architecture_decisions:
        for requirement_id in decision.driven_by_requirements:
            if requirement_id not in known_requirement_ids:
                raise DesignPlanContextValidationError(
                    f"{decision.decision_id} references unknown requirement {requirement_id}"
                )

    active_hard_requirement_ids = {
        requirement.id
        for requirement in all_requirements
        if requirement.enforcement == Enforcement.HARD
        and requirement.status not in {RequirementStatus.REJECTED, RequirementStatus.SUPERSEDED}
    }
    missing = sorted(active_hard_requirement_ids - mapped_or_dispositioned)
    if missing:
        raise DesignPlanContextValidationError(
            f"active hard requirements missing mapping or explicit disposition: {', '.join(missing)}"
        )
