"""Architecture Planner v0.1 orchestration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError

from schematic_ai.application.architecture.context import ArchitecturePlanningContext
from schematic_ai.application.architecture.drafts import DesignPlanDraft
from schematic_ai.application.architecture.enricher import DesignPlanEnricher
from schematic_ai.application.architecture.errors import ArchitectureEnrichmentError, ArchitectureSemanticValidationError
from schematic_ai.application.architecture.prompts import planning_prompt, repair_prompt
from schematic_ai.application.architecture.result import (
    ArchitecturePlanningIssue,
    ArchitecturePlanningResult,
    PlanningIssueReason,
    PlanningResultStatus,
)
from schematic_ai.application.architecture.semantic import validate_architecture_semantics
from schematic_ai.config import load_settings
from schematic_ai.domain.design_plan.models import DesignPlan
from schematic_ai.domain.requirements.enums import Enforcement, RequirementStatus
from schematic_ai.domain.requirements.models import RequirementModel
from schematic_ai.llm.client import LLMClient, LLMClientError


logger = logging.getLogger(__name__)


@dataclass
class ArchitecturePlanner:
    llm_client: LLMClient
    enricher: DesignPlanEnricher = field(default_factory=DesignPlanEnricher)
    max_repair_attempts: int | None = None

    def plan_architecture(
        self,
        requirement_model: RequirementModel,
        *,
        existing_design_plan=None,
        planned_at: datetime | None = None,
    ) -> ArchitecturePlanningResult:
        context = ArchitecturePlanningContext(
            requirement_model=requirement_model,
            existing_design_plan=existing_design_plan,
        )
        requirement_issues = self._requirement_issues(requirement_model)
        if any(issue.blocking for issue in requirement_issues):
            return ArchitecturePlanningResult(
                status=PlanningResultStatus.NEEDS_INPUT,
                requirement_issues=requirement_issues,
            )

        prompt = planning_prompt(context)
        try:
            plan = self._generate_valid_plan(
                prompt=prompt,
                requirement_model=requirement_model,
                existing_design_plan=existing_design_plan,
                created_at=planned_at,
            )
        except (ArchitectureEnrichmentError, ArchitectureSemanticValidationError, ValidationError, LLMClientError, ValueError) as exc:
            return ArchitecturePlanningResult(
                status=PlanningResultStatus.FAILED,
                requirement_issues=[
                    ArchitecturePlanningIssue(
                        issue_type="planning_failed",
                        description=str(exc),
                        blocking=True,
                        reason=PlanningIssueReason.DRAFT,
                    )
                ],
            )

        blocking_open_decisions = [
            decision for decision in plan.open_decisions if decision.blocking and decision.status == "open"
        ]
        if blocking_open_decisions:
            return ArchitecturePlanningResult(
                status=PlanningResultStatus.NEEDS_INPUT,
                design_plan=plan,
                requirement_issues=[
                    ArchitecturePlanningIssue(
                        issue_type="blocking_architecture_decision",
                        description=decision.description,
                        blocking=True,
                        reason=PlanningIssueReason.ARCHITECTURE,
                    )
                    for decision in blocking_open_decisions
                ],
            )

        return ArchitecturePlanningResult(status=PlanningResultStatus.ACCEPTED, design_plan=plan)

    def _generate_valid_plan(
        self,
        *,
        prompt: str,
        requirement_model: RequirementModel,
        existing_design_plan: DesignPlan | None,
        created_at: datetime | None,
    ) -> DesignPlan:
        schema = DesignPlanDraft.model_json_schema()
        attempts_allowed = 1 + self._max_repair_attempts()
        current_prompt = prompt
        last_output = ""
        last_error = ""
        for attempt in range(1, attempts_allowed + 1):
            logger.info("calling architecture llm attempt=%s", attempt)
            raw_output = self.llm_client.generate_structured(prompt=current_prompt, json_schema=schema)
            last_output = raw_output
            try:
                draft = DesignPlanDraft.model_validate_json(raw_output)
                plan = self.enricher.build_design_plan(
                    draft=draft,
                    requirement_model=requirement_model,
                    existing_design_plan=existing_design_plan,
                    created_at=created_at,
                )
                validate_architecture_semantics(requirement_model, plan)
                return plan
            except (
                ArchitectureEnrichmentError,
                ArchitectureSemanticValidationError,
                ValidationError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                last_error = str(exc)
                current_prompt = repair_prompt(
                    original_prompt=prompt,
                    invalid_output=last_output,
                    validation_errors=last_error,
                )
        raise ValueError(f"architecture planning validation failed after {attempts_allowed} attempts: {last_error}")

    def _max_repair_attempts(self) -> int:
        if self.max_repair_attempts is not None:
            return self.max_repair_attempts
        return load_settings().llm_max_repair_attempts

    @staticmethod
    def _requirement_issues(requirement_model: RequirementModel) -> list[ArchitecturePlanningIssue]:
        issues: list[ArchitecturePlanningIssue] = []
        for question in requirement_model.open_questions:
            if question.blocking and question.status == "open":
                issues.append(
                    ArchitecturePlanningIssue(
                        issue_type="blocking_requirement_question",
                        description=question.question,
                        blocking=True,
                        reason=PlanningIssueReason.REQUIREMENT,
                    )
                )

        active_hard = [
            requirement
            for requirement in [*requirement_model.requirements, *requirement_model.derived_requirements]
            if requirement.enforcement == Enforcement.HARD
            and requirement.status not in {RequirementStatus.REJECTED, RequirementStatus.SUPERSEDED}
        ]
        if not active_hard:
            issues.append(
                ArchitecturePlanningIssue(
                    issue_type="no_active_hard_requirements",
                    description="No active hard requirements are available for architecture planning.",
                    blocking=True,
                    reason=PlanningIssueReason.REQUIREMENT,
                )
            )

        return issues
