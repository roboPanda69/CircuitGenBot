"""Architecture planning result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from schematic_ai.domain.design_plan.models import DesignPlan


class PlanningResultStatus(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_INPUT = "needs_input"
    FAILED = "failed"


class PlanningIssueReason(StrEnum):
    REQUIREMENT = "requirement"
    ARCHITECTURE = "architecture"
    DRAFT = "draft"


@dataclass(frozen=True)
class ArchitecturePlanningIssue:
    issue_type: str
    description: str
    blocking: bool
    reason: PlanningIssueReason
    requirement_id: str | None = None


@dataclass(frozen=True)
class ArchitecturePlanningResult:
    status: PlanningResultStatus
    design_plan: DesignPlan | None = None
    requirement_issues: list[ArchitecturePlanningIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.status == PlanningResultStatus.ACCEPTED and self.design_plan is not None

