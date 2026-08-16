"""Typed input context for architecture planning."""

from __future__ import annotations

from dataclasses import dataclass

from schematic_ai.domain.design_plan.models import DesignPlan
from schematic_ai.domain.requirements.models import RequirementModel


@dataclass(frozen=True)
class ArchitecturePlanningContext:
    requirement_model: RequirementModel
    existing_design_plan: DesignPlan | None = None

