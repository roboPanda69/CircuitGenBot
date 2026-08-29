"""Contextual validation for CircuitIR v0.1."""

from __future__ import annotations

from schematic_ai.domain.circuit_ir.enums import ComponentResolutionStatus
from schematic_ai.domain.circuit_ir.models import CircuitIR, KnowledgeReference
from schematic_ai.domain.design_plan.models import DesignPlan
from schematic_ai.domain.knowledge.models import KnowledgeContext


class CircuitIRContextValidationError(ValueError):
    """Raised when a CircuitIR is inconsistent with adjacent project context."""


def validate_circuit_ir_against_design_plan(circuit_ir: CircuitIR, design_plan: DesignPlan) -> None:
    """Validate CircuitIR traceability references against its source DesignPlan.

    This intentionally checks identity and traceability only. It does not infer
    whether selected parts are electrically suitable for the design intent.
    """

    if circuit_ir.source_design_plan.design_plan_id != design_plan.design_plan_id:
        raise CircuitIRContextValidationError("source design_plan_id does not match DesignPlan")
    if circuit_ir.source_design_plan.revision != design_plan.revision:
        raise CircuitIRContextValidationError("source design_plan revision does not match DesignPlan")

    block_ids = {block.block_id for block in design_plan.functional_blocks}
    power_domain_ids = {domain.power_domain_id for domain in design_plan.power_domains}
    interface_ids = {interface.interface_id for interface in design_plan.interfaces}
    known_design_object_ids = design_plan_object_ids(design_plan)

    for component in circuit_ir.components:
        for block_id in component.source_block_ids:
            if block_id not in block_ids:
                raise CircuitIRContextValidationError(
                    f"{component.instance_id} references unknown DesignPlan block {block_id}"
                )

    for net in circuit_ir.nets:
        if net.power_domain_id is not None and net.power_domain_id not in power_domain_ids:
            raise CircuitIRContextValidationError(
                f"{net.net_id} references unknown DesignPlan power domain {net.power_domain_id}"
            )

    for group in circuit_ir.groups:
        for block_id in group.source_block_ids:
            if block_id not in block_ids:
                raise CircuitIRContextValidationError(
                    f"{group.group_id} references unknown DesignPlan block {block_id}"
                )

    for binding in circuit_ir.interface_bindings:
        if binding.design_plan_interface_id not in interface_ids:
            raise CircuitIRContextValidationError(
                f"{binding.binding_id} references unknown DesignPlan interface {binding.design_plan_interface_id}"
            )

    for mapping in circuit_ir.implementation_mappings:
        for object_id in mapping.design_plan_object_ids:
            if object_id not in known_design_object_ids:
                raise CircuitIRContextValidationError(
                    f"{mapping.mapping_id} references unknown DesignPlan object {object_id}"
                )

    for decision in circuit_ir.open_decisions:
        for object_id in decision.driven_by_design_plan_ids:
            if object_id not in known_design_object_ids:
                raise CircuitIRContextValidationError(
                    f"{decision.decision_id} references unknown DesignPlan object {object_id}"
                )


def validate_circuit_ir_against_knowledge(circuit_ir: CircuitIR, knowledge_context: KnowledgeContext) -> None:
    """Validate CircuitIR knowledge references against a KnowledgeContext.

    This checks existence and provenance only. It does not score components,
    compare attributes, verify symbols/footprints, or make selection decisions.
    """

    component_record_ids = {component.component_id for component in knowledge_context.component_records}
    source_ids = {source.source_id for source in knowledge_context.sources}
    evidence_ids = {evidence.evidence_id for evidence in knowledge_context.evidence}

    for component in circuit_ir.components:
        if component.component_record_id is not None and component.component_record_id not in component_record_ids:
            raise CircuitIRContextValidationError(
                f"{component.instance_id} component_record_id is not in KnowledgeContext: "
                f"{component.component_record_id}"
            )
        if component.resolution_status == ComponentResolutionStatus.RESOLVED and component.component_record_id is None:
            raise CircuitIRContextValidationError(f"{component.instance_id} resolved component requires component_record_id")
        if component.symbol_reference is not None and component.symbol_reference.source_id not in source_ids:
            raise CircuitIRContextValidationError(
                f"{component.instance_id} symbol reference source is not in KnowledgeContext: "
                f"{component.symbol_reference.source_id}"
            )
        if component.footprint_reference is not None and component.footprint_reference.source_id not in source_ids:
            raise CircuitIRContextValidationError(
                f"{component.instance_id} footprint reference source is not in KnowledgeContext: "
                f"{component.footprint_reference.source_id}"
            )
        _validate_knowledge_references(
            owner_id=component.instance_id,
            references=component.knowledge_references,
            component_record_ids=component_record_ids,
            source_ids=source_ids,
            evidence_ids=evidence_ids,
        )

    _validate_knowledge_references(
        owner_id=circuit_ir.circuit_id,
        references=circuit_ir.knowledge_references,
        component_record_ids=component_record_ids,
        source_ids=source_ids,
        evidence_ids=evidence_ids,
    )


def design_plan_object_ids(design_plan: DesignPlan) -> set[str]:
    ids = {
        design_plan.design_plan_id,
        *(block.block_id for block in design_plan.functional_blocks),
        *(port.port_id for block in design_plan.functional_blocks for port in [*block.inputs, *block.outputs]),
        *(connection.connection_id for connection in design_plan.block_connections),
        *(domain.power_domain_id for domain in design_plan.power_domains),
        *(interface.interface_id for interface in design_plan.interfaces),
        *(mapping.mapping_id for mapping in design_plan.requirement_mappings),
        *(decision.decision_id for decision in design_plan.architecture_decisions),
        *(assumption.assumption_id for assumption in design_plan.assumptions),
        *(decision.open_decision_id for decision in design_plan.open_decisions),
    }
    return set(ids)


def _validate_knowledge_references(
    *,
    owner_id: str,
    references: list[KnowledgeReference],
    component_record_ids: set[str],
    source_ids: set[str],
    evidence_ids: set[str],
) -> None:
    for reference in references:
        if reference.component_record_id is not None and reference.component_record_id not in component_record_ids:
            raise CircuitIRContextValidationError(
                f"{owner_id} references unknown component_record_id {reference.component_record_id}"
            )
        for source_id in reference.source_ids:
            if source_id not in source_ids:
                raise CircuitIRContextValidationError(f"{owner_id} references unknown source {source_id}")
        for evidence_id in reference.evidence_ids:
            if evidence_id not in evidence_ids:
                raise CircuitIRContextValidationError(f"{owner_id} references unknown evidence {evidence_id}")
