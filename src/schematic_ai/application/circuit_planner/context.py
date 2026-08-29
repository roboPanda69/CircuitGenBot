"""Circuit Planner v0.1 planning context."""

from __future__ import annotations

from dataclasses import dataclass, field

from schematic_ai.domain.circuit_ir import CircuitIR
from schematic_ai.domain.design_plan import DesignPlan
from schematic_ai.domain.knowledge import ComplianceStandard, KnowledgeContext
from schematic_ai.domain.requirements.models import RequirementModel


@dataclass(frozen=True)
class ForcedComponentConstraint:
    target_role: str
    component_record_id: str
    target_design_plan_ids: tuple[str, ...] = ()
    preferred: bool = False


@dataclass(frozen=True)
class CircuitPlannerConfiguration:
    required_qualifications: tuple[ComplianceStandard, ...] = ()
    required_compliance: tuple[ComplianceStandard, ...] = ()
    preferred_qualifications: tuple[ComplianceStandard, ...] = ()
    preferred_compliance: tuple[ComplianceStandard, ...] = ()


@dataclass(frozen=True)
class CircuitPlanningContext:
    requirement_model: RequirementModel
    design_plan: DesignPlan
    knowledge_context: KnowledgeContext
    existing_circuit_ir: CircuitIR | None = None
    forced_component_constraints: tuple[ForcedComponentConstraint, ...] = ()
    planning_metadata: dict[str, str] = field(default_factory=dict)
    configuration: CircuitPlannerConfiguration = field(default_factory=CircuitPlannerConfiguration)
