"""Explainable component candidate evaluation for Circuit Planner v0.1."""

from __future__ import annotations

from dataclasses import dataclass

from schematic_ai.application.circuit_planner.context import CircuitPlanningContext, ForcedComponentConstraint
from schematic_ai.application.circuit_planner.drafts import DraftComponentInstance
from schematic_ai.application.circuit_planner.result import (
    CandidateEligibility,
    ComponentCandidateEvaluation,
    ValueBasisType,
    ValueResolutionBasis,
)
from schematic_ai.domain.circuit_ir import CircuitComponentRole
from schematic_ai.domain.knowledge import (
    AttributeConstraint,
    ComplianceClaim,
    ComplianceStandard,
    ComponentRecord,
    KnowledgeFilter,
    KnowledgeMetadata,
    KnowledgeQuery,
    KnowledgeState,
    QuantityExactValue,
    QuantityMinimumValue,
)
from schematic_ai.domain.knowledge.enums import ComponentCategory
from schematic_ai.domain.requirements.constraints import ExactConstraint, MinimumConstraint, NominalConstraint, RangeConstraint
from schematic_ai.domain.requirements.enums import Enforcement
from schematic_ai.domain.requirements.models import Requirement, RequirementModel


_CLASS_TO_CATEGORY = {
    CircuitComponentRole.CONVERTER: ComponentCategory.POWER_CONVERTER,
    CircuitComponentRole.REGULATOR: ComponentCategory.REGULATOR,
    CircuitComponentRole.CAPACITOR: ComponentCategory.CAPACITOR,
    CircuitComponentRole.INDUCTOR: ComponentCategory.INDUCTOR,
    CircuitComponentRole.RESISTOR: ComponentCategory.RESISTOR,
    CircuitComponentRole.DIODE: ComponentCategory.DIODE,
    CircuitComponentRole.MOSFET: ComponentCategory.MOSFET,
    CircuitComponentRole.CONNECTOR: ComponentCategory.CONNECTOR,
    CircuitComponentRole.PROTECTION_DEVICE: ComponentCategory.PROTECTION_DEVICE,
    CircuitComponentRole.SENSOR: ComponentCategory.SENSOR,
    CircuitComponentRole.INTERFACE_IC: ComponentCategory.INTERFACE_IC,
    CircuitComponentRole.LOGIC: ComponentCategory.LOGIC_IC,
    CircuitComponentRole.OP_AMP: ComponentCategory.OP_AMP,
    CircuitComponentRole.ISOLATOR: ComponentCategory.ISOLATOR,
    CircuitComponentRole.RELAY: ComponentCategory.RELAY,
}


@dataclass(frozen=True)
class CandidateEvaluationBundle:
    selected_component_ids: dict[str, str]
    evaluations: list[ComponentCandidateEvaluation]
    missing_candidate_roles: list[str]
    rejected_forced_constraints: list[ForcedComponentConstraint]
    unknown_forced_constraints: list[ForcedComponentConstraint]
    forced_constraint_conflicts: list[str]


class CircuitCandidateEvaluator:
    def evaluate(self, draft_components: list[DraftComponentInstance], context: CircuitPlanningContext) -> CandidateEvaluationBundle:
        records = {component.component_id: component for component in context.knowledge_context.component_records}
        selected: dict[str, str] = {}
        evaluations: list[ComponentCandidateEvaluation] = []
        missing_roles: list[str] = []
        rejected_forced: list[ForcedComponentConstraint] = []
        unknown_forced: list[ForcedComponentConstraint] = []
        forced_conflicts: list[str] = []

        for component in draft_components:
            forced_matches = matching_forced_constraints(component, context.forced_component_constraints)
            forced_ids = sorted({constraint.component_record_id for constraint in forced_matches})
            if len(forced_ids) > 1:
                forced_conflicts.append(
                    f"{component.draft_id} is forced to multiple component_record_ids: {', '.join(forced_ids)}"
                )
                continue
            forced = forced_matches[0] if forced_matches else None
            candidates = candidates_for_component(component, context)
            if forced is not None:
                record = records.get(forced.component_record_id)
                if record is None:
                    unknown_forced.append(forced)
                    continue
                evaluation = evaluate_component_candidate(component, record, context)
                evaluations.append(evaluation)
                if evaluation.eligibility in {CandidateEligibility.ELIGIBLE, CandidateEligibility.PREFERRED}:
                    selected[component.draft_id] = record.component_id
                else:
                    rejected_forced.append(forced)
                continue

            if component.proposed_component_record_id is not None:
                record = records.get(component.proposed_component_record_id)
                if record is None:
                    raise ValueError(f"unknown ComponentRecord ID proposed by draft: {component.proposed_component_record_id}")
                evaluation = evaluate_component_candidate(component, record, context)
                evaluations.append(evaluation)
                if evaluation.eligibility in {CandidateEligibility.ELIGIBLE, CandidateEligibility.PREFERRED}:
                    selected[component.draft_id] = record.component_id
                else:
                    missing_roles.append(component.draft_id)
                continue

            for record in candidates:
                evaluations.append(evaluate_component_candidate(component, record, context))
            chosen = first_selectable(evaluations, component.draft_id)
            if chosen is not None:
                selected[component.draft_id] = chosen.component_record_id
            elif candidates:
                missing_roles.append(component.draft_id)
            elif should_select_from_knowledge(component):
                missing_roles.append(component.draft_id)

        return CandidateEvaluationBundle(
            selected_component_ids=selected,
            evaluations=evaluations,
            missing_candidate_roles=missing_roles,
            rejected_forced_constraints=rejected_forced,
            unknown_forced_constraints=unknown_forced,
            forced_constraint_conflicts=sorted(set(forced_conflicts)),
        )


def knowledge_query_for_component(
    component: DraftComponentInstance,
    context: CircuitPlanningContext,
    *,
    query_id: str = "KQ_CIRCUIT_PLANNER_001",
) -> KnowledgeQuery:
    return KnowledgeQuery(
        query_id=query_id,
        filters=KnowledgeFilter(
            category=category_for_component(component),
            attribute_constraints=attribute_constraints_for_requirements(context.requirement_model, component),
            required_qualifications=sorted(derived_required_qualifications(context), key=str),
            required_compliance=sorted(context.configuration.required_compliance, key=str),
            preferred_qualifications=sorted(context.configuration.preferred_qualifications, key=str),
            preferred_compliance=sorted(derived_preferred_compliance(context), key=str),
        ),
        metadata=KnowledgeMetadata(created_by="circuit_planner"),
    )


def evaluate_component_candidate(
    component: DraftComponentInstance,
    record: ComponentRecord,
    context: CircuitPlanningContext,
) -> ComponentCandidateEvaluation:
    satisfied: list[str] = []
    preferences: list[str] = []
    unresolved: list[str] = []
    rejections: list[str] = []
    evidence_ids: list[str] = []

    expected_category = category_for_component(component)
    if expected_category is not None and record.category != expected_category:
        rejections.append(f"category {record.category} does not match {expected_category}")

    for constraint in attribute_constraints_for_requirements(context.requirement_model, component):
        state, evidence = evaluate_attribute_constraint(record, constraint)
        evidence_ids.extend(evidence)
        if state == "satisfied":
            satisfied.append(f"attribute:{constraint.name}")
        elif state == "rejected":
            rejections.append(f"attribute:{constraint.name}")
        else:
            unresolved.append(f"attribute:{constraint.name}")

    for standard in derived_required_qualifications(context):
        state, evidence = evaluate_claim(record.qualification_claims, standard)
        evidence_ids.extend(evidence)
        if state == "satisfied":
            satisfied.append(f"qualification:{standard}")
        elif state == "rejected":
            rejections.append(f"qualification:{standard}")
        else:
            unresolved.append(f"qualification:{standard}")

    for standard in context.configuration.required_compliance:
        state, evidence = evaluate_claim(record.compliance_claims, standard)
        evidence_ids.extend(evidence)
        if state == "satisfied":
            satisfied.append(f"compliance:{standard}")
        elif state == "rejected":
            rejections.append(f"compliance:{standard}")
        else:
            unresolved.append(f"compliance:{standard}")

    for standard in context.configuration.preferred_qualifications:
        state, evidence = evaluate_claim(record.qualification_claims, standard)
        evidence_ids.extend(evidence)
        if state == "satisfied":
            preferences.append(f"qualification:{standard}")
        elif state == "unknown":
            unresolved.append(f"preferred_qualification:{standard}")

    for standard in derived_preferred_compliance(context):
        state, evidence = evaluate_claim(record.compliance_claims, standard)
        evidence_ids.extend(evidence)
        if state == "satisfied":
            preferences.append(f"compliance:{standard}")
        elif state == "unknown":
            unresolved.append(f"preferred_compliance:{standard}")

    if rejections:
        eligibility = CandidateEligibility.REJECTED
    elif any(item for item in unresolved if not item.startswith("preferred_")):
        eligibility = CandidateEligibility.UNKNOWN
    elif preferences:
        eligibility = CandidateEligibility.PREFERRED
    else:
        eligibility = CandidateEligibility.ELIGIBLE

    return ComponentCandidateEvaluation(
        target_instance_ref=component.draft_id,
        component_record_id=record.component_id,
        eligibility=eligibility,
        satisfied_constraints=satisfied,
        preference_matches=preferences,
        unresolved_constraints=unresolved,
        rejection_reasons=rejections,
        evidence_ids=sorted(set(evidence_ids)),
        value_resolution_bases=value_resolution_bases_for_record(component, record),
    )


def candidates_for_component(component: DraftComponentInstance, context: CircuitPlanningContext) -> list[ComponentRecord]:
    category = category_for_component(component)
    candidates = []
    for record in sorted(context.knowledge_context.component_records, key=lambda item: item.component_id):
        if category is None or record.category == category:
            candidates.append(record)
    return candidates


def category_for_component(component: DraftComponentInstance):
    return _CLASS_TO_CATEGORY.get(component.component_class)


def should_select_from_knowledge(component: DraftComponentInstance) -> bool:
    return component.component_class in {CircuitComponentRole.CONVERTER, CircuitComponentRole.REGULATOR}


def first_selectable(
    evaluations: list[ComponentCandidateEvaluation],
    target_instance_ref: str,
) -> ComponentCandidateEvaluation | None:
    candidates = sorted(
        [item for item in evaluations if item.target_instance_ref == target_instance_ref],
        key=lambda item: (
            0 if item.eligibility == CandidateEligibility.PREFERRED else 1,
            item.component_record_id,
        ),
    )
    for item in candidates:
        if item.eligibility in {CandidateEligibility.PREFERRED, CandidateEligibility.ELIGIBLE}:
            return item
    return None


def matching_forced_constraints(
    component: DraftComponentInstance,
    constraints: tuple[ForcedComponentConstraint, ...],
) -> list[ForcedComponentConstraint]:
    matches: list[ForcedComponentConstraint] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for constraint in constraints:
        if constraint.target_role == component.role or constraint.target_role == component.draft_id:
            key = (constraint.target_role, constraint.component_record_id, tuple(sorted(constraint.target_design_plan_ids)))
            if key not in seen:
                matches.append(constraint)
                seen.add(key)
            continue
        if constraint.target_design_plan_ids and set(constraint.target_design_plan_ids) & set(component.source_design_plan_refs):
            key = (constraint.target_role, constraint.component_record_id, tuple(sorted(constraint.target_design_plan_ids)))
            if key not in seen:
                matches.append(constraint)
                seen.add(key)
    return matches


def attribute_constraints_for_requirements(
    requirement_model: RequirementModel,
    component: DraftComponentInstance,
) -> list[AttributeConstraint]:
    if component.component_class not in {CircuitComponentRole.CONVERTER, CircuitComponentRole.REGULATOR}:
        return []
    constraints: list[AttributeConstraint] = []
    for requirement in active_hard_requirements(requirement_model):
        if requirement.type == "input_voltage" and isinstance(requirement.constraint, (ExactConstraint, NominalConstraint)):
            constraints.append(
                AttributeConstraint(
                    name="input_voltage",
                    required_value=QuantityExactValue(
                        value={"value": requirement.constraint.value, "unit": requirement.constraint.unit}
                    ),
                )
            )
        if requirement.type == "input_voltage" and isinstance(requirement.constraint, RangeConstraint):
            constraints.append(
                AttributeConstraint(
                    name="input_voltage",
                    required_value=QuantityExactValue(
                        value={"value": requirement.constraint.maximum, "unit": requirement.constraint.unit}
                    ),
                )
            )
        if requirement.type == "output_current" and isinstance(requirement.constraint, MinimumConstraint):
            constraints.append(
                AttributeConstraint(
                    name="maximum_output_current",
                    required_value=QuantityMinimumValue(
                        value={"value": requirement.constraint.value, "unit": requirement.constraint.unit}
                    ),
                )
            )
    return constraints


def active_hard_requirements(requirement_model: RequirementModel) -> list[Requirement]:
    return [
        requirement
        for requirement in [*requirement_model.requirements, *requirement_model.derived_requirements]
        if requirement.enforcement == Enforcement.HARD and requirement.status not in {"rejected", "superseded"}
    ]


def derived_required_qualifications(context: CircuitPlanningContext) -> set[ComplianceStandard]:
    standards = set(context.configuration.required_qualifications)
    standards.update(standards_from_requirements(context.requirement_model, hard=True, qualification=True))
    return standards


def derived_preferred_compliance(context: CircuitPlanningContext) -> set[ComplianceStandard]:
    standards = set(context.configuration.preferred_compliance)
    standards.update(standards_from_requirements(context.requirement_model, hard=False, qualification=False))
    return standards


def standards_from_requirements(
    requirement_model: RequirementModel,
    *,
    hard: bool,
    qualification: bool,
) -> set[ComplianceStandard]:
    result: set[ComplianceStandard] = set()
    for requirement in [*requirement_model.requirements, *requirement_model.derived_requirements]:
        is_hard = requirement.enforcement == Enforcement.HARD
        if hard != is_hard:
            continue
        text = " ".join([requirement.type, requirement.description, *requirement.tags]).upper().replace("-", "_")
        if qualification and "AEC_Q100" in text:
            result.add(ComplianceStandard.AEC_Q100)
        if not qualification and "ISO_26262" in text:
            result.add(ComplianceStandard.ISO_26262)
    return result


def evaluate_attribute_constraint(record: ComponentRecord, constraint: AttributeConstraint) -> tuple[str, list[str]]:
    matching_attributes = [
        attribute
        for attribute in record.attributes
        if attribute.name == constraint.name and attribute.status == KnowledgeState.VERIFIED and attribute.value is not None
    ]
    evidence_ids = [evidence_id for attribute in matching_attributes for evidence_id in attribute.evidence_ids]
    if not matching_attributes:
        return "unknown", evidence_ids
    if any(attribute_value_satisfies(attribute.value, constraint.required_value) for attribute in matching_attributes):
        return "satisfied", evidence_ids
    return "rejected", evidence_ids


def attribute_value_satisfies(known, required) -> bool:
    known_interval = quantity_interval(known)
    if known_interval is None:
        return known == required
    if isinstance(required, (QuantityExactValue,)):
        return interval_contains(known_interval, required.value.value, required.value.unit)
    if isinstance(required, QuantityMinimumValue):
        return known_interval[1] >= required.value.value and known_interval[2] == required.value.unit
    return False


def quantity_interval(value) -> tuple[float, float, str] | None:
    kind = getattr(value, "kind", None)
    if kind in {"exact", "nominal"}:
        return (value.value.value, value.value.value, value.value.unit)
    if kind == "range":
        return (value.minimum.value, value.maximum.value, value.minimum.unit)
    if kind == "minimum":
        return (value.value.value, float("inf"), value.value.unit)
    if kind == "maximum":
        return (float("-inf"), value.value.value, value.value.unit)
    return None


def interval_contains(interval: tuple[float, float, str], value: float, unit: str) -> bool:
    minimum, maximum, interval_unit = interval
    return interval_unit == unit and minimum <= value <= maximum


def evaluate_claim(claims: list[ComplianceClaim], standard: ComplianceStandard) -> tuple[str, list[str]]:
    matching = [claim for claim in claims if claim.standard == standard]
    evidence_ids = [evidence_id for claim in matching for evidence_id in claim.evidence_ids]
    if any(claim.evidence_state == KnowledgeState.VERIFIED_NO for claim in matching):
        return "rejected", evidence_ids
    if any(claim.evidence_state == KnowledgeState.VERIFIED for claim in matching):
        return "satisfied", evidence_ids
    return "unknown", evidence_ids


def value_resolution_bases_for_record(
    component: DraftComponentInstance,
    record: ComponentRecord,
) -> list[ValueResolutionBasis]:
    bases: list[ValueResolutionBasis] = []
    for attribute in record.attributes:
        if attribute.status != KnowledgeState.VERIFIED or attribute.value is None or not attribute.evidence_ids:
            continue
        if attribute.name not in recognized_value_attribute_names(component):
            continue
        bases.append(
            ValueResolutionBasis(
                basis_type=ValueBasisType.COMPONENT_ATTRIBUTE,
                component_attribute_ids=[attribute.attribute_id],
                evidence_ids=attribute.evidence_ids,
            )
        )
    return bases


def recognized_value_attribute_names(component: DraftComponentInstance) -> set[str]:
    by_class = {
        CircuitComponentRole.CAPACITOR: {
            "capacitance",
            "recommended_capacitance",
            "recommended_input_capacitance",
            "recommended_output_capacitance",
        },
        CircuitComponentRole.INDUCTOR: {"inductance", "recommended_inductance"},
        CircuitComponentRole.RESISTOR: {"resistance", "recommended_resistance"},
    }
    return by_class.get(component.component_class, set())
