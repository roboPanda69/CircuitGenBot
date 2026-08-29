"""Circuit Planner v0.1 orchestration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError

from schematic_ai.application.circuit_planner.context import CircuitPlanningContext
from schematic_ai.application.circuit_planner.drafts import CircuitIRDraft
from schematic_ai.application.circuit_planner.enricher import CircuitIREnricher
from schematic_ai.application.circuit_planner.evaluation import (
    CircuitCandidateEvaluator,
    knowledge_query_for_component,
)
from schematic_ai.application.circuit_planner.prompts import planning_prompt, repair_prompt
from schematic_ai.application.circuit_planner.result import (
    CandidateEligibility,
    CircuitPlanningIssue,
    CircuitPlanningIssueType,
    CircuitPlanningResult,
    CircuitPlanningStatus,
)
from schematic_ai.config import load_settings
from schematic_ai.domain.circuit_ir import (
    CircuitIR,
    validate_circuit_ir_against_design_plan,
    validate_circuit_ir_against_knowledge,
)
from schematic_ai.domain.design_plan import RequirementMappingStatus, validate_design_plan_against_requirements
from schematic_ai.llm.client import LLMClient, LLMClientError


logger = logging.getLogger(__name__)


@dataclass
class CircuitPlanner:
    llm_client: LLMClient
    enricher: CircuitIREnricher = field(default_factory=CircuitIREnricher)
    evaluator: CircuitCandidateEvaluator = field(default_factory=CircuitCandidateEvaluator)
    max_repair_attempts: int | None = None

    def plan_circuit(self, context: CircuitPlanningContext, *, planned_at: datetime | None = None) -> CircuitPlanningResult:
        upfront_issues = self._upfront_issues(context)
        if any(issue.blocking for issue in upfront_issues):
            return CircuitPlanningResult(
                status=CircuitPlanningStatus.NEEDS_INPUT,
                issues=upfront_issues,
                diagnostics={"attempts": 0},
            )

        prompt = planning_prompt(context)
        try:
            return self._generate_valid_result(prompt=prompt, context=context, planned_at=planned_at, base_issues=upfront_issues)
        except (ValidationError, LLMClientError, ValueError) as exc:
            return CircuitPlanningResult(
                status=CircuitPlanningStatus.FAILED,
                issues=[
                    CircuitPlanningIssue(
                        issue_id="CPI_FAILED_001",
                        issue_type=CircuitPlanningIssueType.INVALID_DRAFT,
                        target_ids=[],
                        description=str(exc),
                        blocking=True,
                    )
                ],
                diagnostics={"attempts": 1 + self._max_repair_attempts()},
            )

    def _generate_valid_result(
        self,
        *,
        prompt: str,
        context: CircuitPlanningContext,
        planned_at: datetime | None,
        base_issues: list[CircuitPlanningIssue],
    ) -> CircuitPlanningResult:
        schema = CircuitIRDraft.model_json_schema()
        attempts_allowed = 1 + self._max_repair_attempts()
        current_prompt = prompt
        last_output = ""
        last_error = ""
        for attempt in range(1, attempts_allowed + 1):
            logger.info("calling circuit planner llm attempt=%s", attempt)
            raw_output = self.llm_client.generate_structured(prompt=current_prompt, json_schema=schema)
            last_output = raw_output
            try:
                draft = CircuitIRDraft.model_validate_json(raw_output)
                return self._build_result_from_draft(
                    draft=draft,
                    context=context,
                    planned_at=planned_at,
                    attempt=attempt,
                    base_issues=base_issues,
                )
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)
                current_prompt = repair_prompt(
                    original_prompt=prompt,
                    invalid_output=last_output,
                    validation_errors=last_error,
                )
        raise ValueError(f"circuit planning validation failed after {attempts_allowed} attempts: {last_error}")

    def _build_result_from_draft(
        self,
        *,
        draft: CircuitIRDraft,
        context: CircuitPlanningContext,
        planned_at: datetime | None,
        attempt: int,
        base_issues: list[CircuitPlanningIssue],
    ) -> CircuitPlanningResult:
        bundle = self.evaluator.evaluate(draft.component_instances, context)
        candidate_issues = issues_from_candidate_bundle(bundle)
        coverage_issues = issues_from_design_plan_coverage(draft, context, len(base_issues) + len(candidate_issues))
        issues = [*base_issues, *candidate_issues, *coverage_issues]
        circuit_ir = self.enricher.build_circuit_ir(
            draft=draft,
            context=context,
            selected_component_ids=bundle.selected_component_ids,
            planning_issues=issues,
            created_at=planned_at,
        )
        validate_circuit_ir_against_design_plan(circuit_ir, context.design_plan)
        validate_circuit_ir_against_knowledge(circuit_ir, context.knowledge_context)

        forced_blockers = [
            issue
            for issue in issues
            if issue.blocking and issue.issue_type in {CircuitPlanningIssueType.KNOWLEDGE_MISSING, CircuitPlanningIssueType.CONSTRAINT_CONFLICT}
        ]
        if forced_blockers:
            status = CircuitPlanningStatus.NEEDS_INPUT
        elif circuit_ir.implementation_status == "resolved" and not any(
            issue.issue_type == CircuitPlanningIssueType.INCOMPLETE_ARCHITECTURE for issue in issues
        ):
            status = CircuitPlanningStatus.ACCEPTED
        else:
            status = CircuitPlanningStatus.PARTIAL
            if not issues:
                issues.append(
                    CircuitPlanningIssue(
                        issue_id=f"CPI_{len(issues) + 1:03d}",
                        issue_type=CircuitPlanningIssueType.IMPLEMENTATION_AMBIGUITY,
                        target_ids=[],
                        description="CircuitIR remains partially resolved for progressive synthesis.",
                        blocking=False,
                    )
                )

        knowledge_query_ids = [
            knowledge_query_for_component(component, context, query_id=f"KQ_CIRCUIT_PLANNER_{index:03d}").query_id
            for index, component in enumerate(draft.component_instances, start=1)
        ]
        return CircuitPlanningResult(
            status=status,
            circuit_ir=circuit_ir,
            issues=issues,
            candidate_evaluations=bundle.evaluations,
            diagnostics={"attempts": attempt, "knowledge_query_ids": knowledge_query_ids},
        )

    def _max_repair_attempts(self) -> int:
        if self.max_repair_attempts is not None:
            return self.max_repair_attempts
        return load_settings().llm_max_repair_attempts

    @staticmethod
    def _upfront_issues(context: CircuitPlanningContext) -> list[CircuitPlanningIssue]:
        issues: list[CircuitPlanningIssue] = []
        if context.requirement_model.project_id != context.design_plan.project_id:
            issues.append(
                CircuitPlanningIssue(
                    issue_id="CPI_CTX_001",
                    issue_type=CircuitPlanningIssueType.INCOMPLETE_ARCHITECTURE,
                    target_ids=[context.design_plan.design_plan_id],
                    description="RequirementModel project_id does not match DesignPlan project_id.",
                    blocking=True,
                )
            )
        if context.existing_circuit_ir is not None:
            existing = context.existing_circuit_ir
            if existing.project_id != context.design_plan.project_id:
                issues.append(
                    CircuitPlanningIssue(
                        issue_id="CPI_CTX_002",
                        issue_type=CircuitPlanningIssueType.INCOMPLETE_ARCHITECTURE,
                        target_ids=[existing.circuit_id],
                        description="Existing CircuitIR project_id does not match current DesignPlan project_id.",
                        blocking=True,
                    )
                )
            if existing.source_design_plan.design_plan_id != context.design_plan.design_plan_id:
                issues.append(
                    CircuitPlanningIssue(
                        issue_id="CPI_CTX_003",
                        issue_type=CircuitPlanningIssueType.INCOMPLETE_ARCHITECTURE,
                        target_ids=[existing.circuit_id],
                        description="Existing CircuitIR source DesignPlan lineage does not match current DesignPlan.",
                        blocking=True,
                    )
                )
            if existing.source_design_plan.revision != context.design_plan.revision:
                issues.append(
                    CircuitPlanningIssue(
                        issue_id="CPI_CTX_004",
                        issue_type=CircuitPlanningIssueType.INCOMPLETE_ARCHITECTURE,
                        target_ids=[existing.circuit_id],
                        description="Existing CircuitIR source DesignPlan revision does not match current DesignPlan revision.",
                        blocking=True,
                    )
                )
        try:
            validate_design_plan_against_requirements(context.design_plan, context.requirement_model)
        except Exception as exc:
            issues.append(
                CircuitPlanningIssue(
                    issue_id="CPI_ARCH_001",
                    issue_type=CircuitPlanningIssueType.INCOMPLETE_ARCHITECTURE,
                    target_ids=[context.design_plan.design_plan_id],
                    description=str(exc),
                    blocking=True,
                )
            )
        if not context.design_plan.functional_blocks:
            issues.append(
                CircuitPlanningIssue(
                    issue_id="CPI_ARCH_002",
                    issue_type=CircuitPlanningIssueType.INCOMPLETE_ARCHITECTURE,
                    target_ids=[context.design_plan.design_plan_id],
                    description="DesignPlan has no functional blocks to implement.",
                    blocking=True,
                )
            )
        return issues


def issues_from_candidate_bundle(bundle) -> list[CircuitPlanningIssue]:
    issues: list[CircuitPlanningIssue] = []
    for conflict in bundle.forced_constraint_conflicts:
        issues.append(
            CircuitPlanningIssue(
                issue_id=f"CPI_{len(issues) + 1:03d}",
                issue_type=CircuitPlanningIssueType.CONSTRAINT_CONFLICT,
                target_ids=[],
                description=conflict,
                blocking=True,
            )
        )
    for forced in bundle.unknown_forced_constraints:
        issues.append(
            CircuitPlanningIssue(
                issue_id=f"CPI_{len(issues) + 1:03d}",
                issue_type=CircuitPlanningIssueType.KNOWLEDGE_MISSING,
                target_ids=[],
                description=f"Forced component {forced.component_record_id} is not present in the supplied KnowledgeContext.",
                blocking=True,
                related_design_plan_ids=list(forced.target_design_plan_ids),
            )
        )
    for forced in bundle.rejected_forced_constraints:
        issues.append(
            CircuitPlanningIssue(
                issue_id=f"CPI_{len(issues) + 1:03d}",
                issue_type=CircuitPlanningIssueType.CONSTRAINT_CONFLICT,
                target_ids=[],
                description=f"Forced component {forced.component_record_id} does not satisfy known hard constraints.",
                blocking=True,
                related_design_plan_ids=list(forced.target_design_plan_ids),
            )
        )
    for role in bundle.missing_candidate_roles:
        issue_type = CircuitPlanningIssueType.KNOWLEDGE_MISSING
        if any(item.target_instance_ref == role and item.eligibility == CandidateEligibility.REJECTED for item in bundle.evaluations):
            issue_type = CircuitPlanningIssueType.NO_CANDIDATE
        issues.append(
            CircuitPlanningIssue(
                issue_id=f"CPI_{len(issues) + 1:03d}",
                issue_type=issue_type,
                target_ids=[role],
                description=f"No confirmed eligible component is available for draft instance {role}.",
                blocking=False,
            )
        )
    return issues


def issues_from_design_plan_coverage(
    draft: CircuitIRDraft,
    context: CircuitPlanningContext,
    existing_issue_count: int,
) -> list[CircuitPlanningIssue]:
    scoped_design_ids = draft_design_scope(draft)
    issues: list[CircuitPlanningIssue] = []
    for design_object_id, coverage in sorted(relevant_design_scope(context).items()):
        if design_object_id in scoped_design_ids:
            continue
        blocking = bool(coverage["hard_requirement_ids"])
        requirement_ids = [*coverage["hard_requirement_ids"], *coverage["soft_requirement_ids"]]
        issues.append(
            CircuitPlanningIssue(
                issue_id=f"CPI_{existing_issue_count + len(issues) + 1:03d}",
                issue_type=CircuitPlanningIssueType.INCOMPLETE_ARCHITECTURE,
                target_ids=[design_object_id],
                description=f"DesignPlan object {design_object_id} is planned architecture but is outside this Circuit Planner draft scope.",
                blocking=blocking,
                related_requirement_ids=requirement_ids,
                related_design_plan_ids=[design_object_id],
            )
        )
    return issues


def draft_design_scope(draft: CircuitIRDraft) -> set[str]:
    scoped: set[str] = set()
    for component in draft.component_instances:
        scoped.update(component.source_design_plan_refs)
    for net in draft.nets:
        if net.power_domain_ref is not None:
            scoped.add(net.power_domain_ref)
    for mapping in draft.implementation_mappings:
        if mapping.circuit_draft_refs:
            scoped.update(mapping.design_plan_refs)
    return scoped


def relevant_design_scope(context: CircuitPlanningContext) -> dict[str, dict[str, list[str]]]:
    requirements_by_id = {
        requirement.id: requirement
        for requirement in [*context.requirement_model.requirements, *context.requirement_model.derived_requirements]
        if requirement.status not in {"rejected", "superseded"}
    }
    relevant: dict[str, dict[str, set[str]]] = {}

    for block in context.design_plan.functional_blocks:
        add_coverage_target(relevant, block.block_id)
    for interface in context.design_plan.interfaces:
        add_coverage_target(relevant, interface.interface_id)
    for power_domain in context.design_plan.power_domains:
        add_coverage_target(relevant, power_domain.power_domain_id)
    for connection in context.design_plan.block_connections:
        add_coverage_target(relevant, connection.connection_id)

    for mapping in context.design_plan.requirement_mappings:
        requirement = requirements_by_id.get(mapping.requirement_id)
        if requirement is None:
            continue
        if mapping.status not in {RequirementMappingStatus.MAPPED, RequirementMappingStatus.PARTIALLY_MAPPED}:
            continue
        for target in mapping.implemented_by:
            entry = add_coverage_target(relevant, target.id)
            key = "hard_requirement_ids" if requirement.enforcement == "hard" else "soft_requirement_ids"
            entry[key].add(mapping.requirement_id)

    return {
        object_id: {
            "hard_requirement_ids": sorted(values["hard_requirement_ids"]),
            "soft_requirement_ids": sorted(values["soft_requirement_ids"]),
        }
        for object_id, values in relevant.items()
    }


def add_coverage_target(relevant: dict[str, dict[str, set[str]]], target_id: str) -> dict[str, set[str]]:
    return relevant.setdefault(target_id, {"hard_requirement_ids": set(), "soft_requirement_ids": set()})
