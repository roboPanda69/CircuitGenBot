"""Prompt templates for architecture planning."""

from __future__ import annotations

from schematic_ai.application.architecture.context import ArchitecturePlanningContext
from schematic_ai.domain.design_plan.models import DesignPlan
from schematic_ai.domain.requirements.models import RequirementModel


SYSTEM_INSTRUCTIONS = """You propose functional architecture as JSON only.
Use only the supplied RequirementModel and optional existing DesignPlan.
Do not invent missing user requirements.
Do not select components, manufacturers, part numbers, values, pins, nets, KiCad symbols, footprints, SPICE models, or circuit implementation details.
Use controlled architecture enums only.
Map every active hard requirement to mapped, partially_mapped, unresolved, or not_applicable.
Missing WHAT belongs to requirement issues; missing HOW belongs to open architecture decisions.
Return only valid JSON for the requested DesignPlanDraft schema."""


def planning_prompt(context: ArchitecturePlanningContext) -> str:
    existing = ""
    if context.existing_design_plan is not None:
        existing = "\nExisting DesignPlan summary:\n" + summarize_design_plan(context.existing_design_plan)
    return f"""{SYSTEM_INSTRUCTIONS}

Task: Propose a DesignPlanDraft for this RequirementModel.

RequirementModel summary:
{summarize_requirement_model(context.requirement_model)}
{existing}
"""


def repair_prompt(
    *,
    original_prompt: str,
    invalid_output: str,
    validation_errors: str,
) -> str:
    return f"""{SYSTEM_INSTRUCTIONS}

The previous output was invalid for DesignPlanDraft. Return corrected JSON only.

Validation errors:
{validation_errors}

Invalid output:
{invalid_output}

Original task:
{original_prompt}
"""


def summarize_requirement_model(model: RequirementModel) -> str:
    lines = [
        f"Requirement set: {model.requirement_set_id} revision {model.revision}",
        f"Project: {model.project_id}",
    ]
    for requirement in [*model.requirements, *model.derived_requirements]:
        lines.append(
            f"- {requirement.id}: status={requirement.status} enforcement={requirement.enforcement} "
            f"category={requirement.category} type={requirement.type} "
            f"constraint={requirement.constraint.model_dump(mode='json')}"
        )
    if model.open_questions:
        lines.append("Open requirement questions:")
        for question in model.open_questions:
            lines.append(f"- {question.id}: blocking={question.blocking} {question.question}")
    return "\n".join(lines)


def summarize_design_plan(model: DesignPlan) -> str:
    lines = [
        f"Design plan: {model.design_plan_id} revision {model.revision}",
    ]
    for block in model.functional_blocks:
        lines.append(f"- {block.block_id}: {block.type} {block.name} topology={block.topology_class}")
    return "\n".join(lines)

