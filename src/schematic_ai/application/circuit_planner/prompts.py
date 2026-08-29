"""Prompt templates for Circuit Planner v0.1."""

from __future__ import annotations

from schematic_ai.application.architecture.prompts import summarize_requirement_model
from schematic_ai.application.circuit_planner.context import CircuitPlanningContext


SYSTEM_INSTRUCTIONS = """You propose electrical implementation drafts as JSON only.
Return only valid JSON for the requested CircuitIRDraft schema.
Use temporary draft IDs only; deterministic code owns canonical CircuitIR IDs.
Do not invent ComponentRecord IDs, manufacturers, part numbers, pin numbers, or values.
Select components only by supplied component_record_id values.
Use the supplied DesignPlan as the architecture source; do not redesign the architecture.
For draft assumptions, use a stable semantic_topic; do not rely on wording to identify an assumption.
Open implementation decisions may explain unresolved work, but they do not count as implementation coverage.
Progressive unresolved implementation is allowed.
Do not generate KiCad, SKiDL, SPICE, verification, PCB, or layout artifacts."""


def planning_prompt(context: CircuitPlanningContext) -> str:
    existing = ""
    if context.existing_circuit_ir is not None:
        existing = "\nExisting CircuitIR summary:\n" + summarize_existing_circuit(context)
    return f"""{SYSTEM_INSTRUCTIONS}

Task: Propose a CircuitIRDraft for this planning context.

RequirementModel summary:
{summarize_requirement_model(context.requirement_model)}

DesignPlan summary:
{summarize_design_plan(context)}

Known ComponentRecord IDs:
{summarize_knowledge(context)}

Engineering rules:
{summarize_rules(context)}
{existing}
"""


def repair_prompt(
    *,
    original_prompt: str,
    invalid_output: str,
    validation_errors: str,
) -> str:
    return f"""{SYSTEM_INSTRUCTIONS}

The previous output was invalid for CircuitIRDraft or deterministic CircuitIR enrichment.
Return corrected JSON only.

Validation errors:
{validation_errors}

Invalid output:
{invalid_output}

Original task:
{original_prompt}
"""


def summarize_design_plan(context: CircuitPlanningContext) -> str:
    plan = context.design_plan
    lines = [f"DesignPlan: {plan.design_plan_id} revision {plan.revision}"]
    for block in plan.functional_blocks:
        lines.append(f"- {block.block_id}: type={block.type} topology={block.topology_class} name={block.name}")
    for domain in plan.power_domains:
        lines.append(f"- {domain.power_domain_id}: role={domain.role} voltage={domain.voltage.model_dump(mode='json') if domain.voltage else None}")
    for interface in plan.interfaces:
        lines.append(f"- {interface.interface_id}: type={interface.type} participants={interface.participants}")
    return "\n".join(lines)


def summarize_knowledge(context: CircuitPlanningContext) -> str:
    if not context.knowledge_context.component_records:
        return "- none"
    return "\n".join(
        f"- {component.component_id}: category={component.category} manufacturer={component.manufacturer} part={component.part_number}"
        for component in context.knowledge_context.component_records
    )


def summarize_rules(context: CircuitPlanningContext) -> str:
    if not context.knowledge_context.engineering_rules:
        return "- none"
    return "\n".join(
        f"- {rule.rule_id}: category={rule.category} applicability={rule.applicability.model_dump(mode='json')}"
        for rule in context.knowledge_context.engineering_rules
    )


def summarize_existing_circuit(context: CircuitPlanningContext) -> str:
    assert context.existing_circuit_ir is not None
    circuit = context.existing_circuit_ir
    lines = [f"CircuitIR: {circuit.circuit_id} revision {circuit.revision} status={circuit.implementation_status}"]
    for component in circuit.components:
        lines.append(
            f"- {component.instance_id}: class={component.component_class} role={component.role} "
            f"record={component.component_record_id} status={component.resolution_status}"
        )
    return "\n".join(lines)
