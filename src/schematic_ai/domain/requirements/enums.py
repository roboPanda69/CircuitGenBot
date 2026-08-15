"""Controlled vocabularies for RequirementModel v0.1."""

from __future__ import annotations

from enum import StrEnum


class RequirementCategory(StrEnum):
    POWER = "power"
    FUNCTIONAL = "functional"
    INTERFACE = "interface"
    PROTECTION = "protection"
    ELECTRICAL = "electrical"
    PERFORMANCE = "performance"
    ENVIRONMENTAL = "environmental"
    PHYSICAL = "physical"
    COMPONENT = "component"
    MANUFACTURING = "manufacturing"
    COST = "cost"
    RELIABILITY = "reliability"
    SAFETY = "safety"
    USER_PREFERENCE = "user_preference"
    OTHER = "other"


class RequirementPriority(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"
    PREFERENCE = "preference"


class Enforcement(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    ADVISORY = "advisory"


class RequirementStatus(StrEnum):
    CANDIDATE = "candidate"
    NEEDS_CLARIFICATION = "needs_clarification"
    CONFIRMED = "confirmed"
    DERIVED = "derived"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class OriginType(StrEnum):
    USER = "user"
    DERIVED = "derived"
    ENGINEERING_RULE = "engineering_rule"
    DATASHEET = "datasheet"
    DEFAULT = "default"
    AI_ASSUMPTION = "ai_assumption"
    IMPORTED = "imported"


class AssumptionSource(StrEnum):
    USER = "user"
    AI = "ai"
    ENGINEERING_RULE = "engineering_rule"
    DEFAULT = "default"
    DATASHEET = "datasheet"
    IMPORTED = "imported"


class Impact(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QuestionStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    DISMISSED = "dismissed"


class QuestionImportance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RelationshipType(StrEnum):
    DERIVED_FROM = "derived_from"
    REQUIRES = "requires"
    CONFLICTS_WITH = "conflicts_with"
    REFINES = "refines"
    SUPERSEDES = "supersedes"


class ConflictType(StrEnum):
    MUTUALLY_INCOMPATIBLE = "mutually_incompatible"
    AMBIGUOUS = "ambiguous"
    RESOURCE_CONTENTION = "resource_contention"
    NEEDS_HUMAN_DECISION = "needs_human_decision"


class ConflictSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class ConflictResolutionStatus(StrEnum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class TargetType(StrEnum):
    SYSTEM = "system"
    POWER_INPUT = "power_input"
    POWER_OUTPUT = "power_output"
    POWER_RAIL = "power_rail"
    INTERFACE = "interface"
    FUNCTIONAL_BLOCK = "functional_block"
    CONNECTOR = "connector"
    COMPONENT = "component"
    SIGNAL = "signal"
    LOGICAL = "logical"


class VerificationMethod(StrEnum):
    CONNECTIVITY = "connectivity"
    ERC = "erc"
    DATASHEET_CONSTRAINT = "datasheet_constraint"
    ENGINEERING_RULE = "engineering_rule"
    ELECTRICAL_CALCULATION = "electrical_calculation"
    SIMULATION = "simulation"
    MANUAL_REVIEW = "manual_review"
    HARDWARE_TEST = "hardware_test"
    VISUAL_INSPECTION = "visual_inspection"
    NOT_YET_DEFINED = "not_yet_defined"
