"""Prompt templates for requirement interpretation."""

from __future__ import annotations

from schematic_ai.application.requirements.drafts import MessageEnvelope
from schematic_ai.domain.requirements.models import RequirementModel


SYSTEM_INSTRUCTIONS = """You extract electronics requirements into JSON only.
Do not design circuits, choose parts, produce KiCad/SKiDL/SPICE, or invent engineering rules.
Extract only user-supported intent. Preserve nominal/minimum/maximum/range/tolerance semantics.
Represent preferences as preferences, assumptions separately, and important missing information as open questions.
Return only valid JSON for the requested schema."""


def extraction_prompt(message: MessageEnvelope) -> str:
    return f"""{SYSTEM_INSTRUCTIONS}

Task: Convert this first user message into a RequirementExtractionDraft JSON object.

Message ID: {message.message_id}
Project ID: {message.project_id}
User message:
{message.text}
"""


def change_prompt(message: MessageEnvelope, current_model: RequirementModel) -> str:
    return f"""{SYSTEM_INSTRUCTIONS}

Task: Convert this follow-up user message into a RequirementChangeDraft JSON object.
Use existing requirement IDs when modifying/removing requirements. If the requested change is ambiguous, return an ask_open_question operation.

Current requirements:
{summarize_requirements(current_model)}

Message ID: {message.message_id}
Project ID: {message.project_id}
User message:
{message.text}
"""


def repair_prompt(
    *,
    original_prompt: str,
    invalid_output: str,
    validation_errors: str,
    schema_name: str,
) -> str:
    return f"""{SYSTEM_INSTRUCTIONS}

The previous output was invalid for {schema_name}. Return corrected JSON only.

Validation errors:
{validation_errors}

Invalid output:
{invalid_output}

Original task:
{original_prompt}
"""


def summarize_requirements(model: RequirementModel) -> str:
    lines = []
    for requirement in model.requirements:
        lines.append(
            f"- {requirement.id}: {requirement.category} {requirement.type} "
            f"{requirement.constraint.model_dump(mode='json')}"
        )
    if not lines:
        return "- none"
    return "\n".join(lines)

