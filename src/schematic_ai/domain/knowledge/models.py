"""Engineering Knowledge Foundation v0.1 typed contracts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schematic_ai.domain.knowledge.enums import (
    ComplianceClaimType,
    ComplianceDomain,
    ComplianceStandard,
    ComponentCategory,
    DocumentationStatus,
    EngineeringRuleCategory,
    EngineeringRuleSeverity,
    EngineeringRuleStatus,
    EvidenceValidationMethod,
    ExtractionMethod,
    KnowledgeImportMode,
    KnowledgeImportStatus,
    KnowledgeSourceType,
    KnowledgeState,
    LifecycleStatus,
    SourceReferenceType,
    SourceTrustClass,
)
from schematic_ai.domain.requirements.constraints import Condition, Quantity
from schematic_ai.domain.requirements.validation import (
    reject_duplicates,
    require_finite_number,
    require_identifier,
    require_nonblank,
)


SCHEMA_VERSION = "0.1"

_FORBIDDEN_COMPONENT_FIELDS = {
    "recommended_for_block",
    "selected_for_design",
    "ranking_score",
    "best_candidate",
    "chosen_component",
}


class KnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class KnowledgeMetadata(KnowledgeModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("created_by")
    @classmethod
    def created_by_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "created_by")

    @model_validator(mode="after")
    def updated_at_must_not_precede_created_at(self) -> "KnowledgeMetadata":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be greater than or equal to created_at")
        return self


class ComponentIdentity(KnowledgeModel):
    manufacturer: str
    part_number: str
    variant: str | None = None

    @field_validator("manufacturer", "part_number")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "component identity")

    @field_validator("variant")
    @classmethod
    def optional_variant_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "variant")

    def canonical_key(self) -> tuple[str, str, str | None]:
        return (canonical_identity_text(self.manufacturer), canonical_identity_text(self.part_number), canonical_identity_text(self.variant) if self.variant else None)


class QuantityExactValue(KnowledgeModel):
    kind: Literal["exact"] = "exact"
    value: Quantity


class QuantityNominalValue(KnowledgeModel):
    kind: Literal["nominal"] = "nominal"
    value: Quantity


class QuantityMinimumValue(KnowledgeModel):
    kind: Literal["minimum"] = "minimum"
    value: Quantity


class QuantityMaximumValue(KnowledgeModel):
    kind: Literal["maximum"] = "maximum"
    value: Quantity


class QuantityRangeValue(KnowledgeModel):
    kind: Literal["range"] = "range"
    minimum: Quantity
    maximum: Quantity

    @model_validator(mode="after")
    def range_units_and_order_must_be_valid(self) -> "QuantityRangeValue":
        if self.minimum.unit != self.maximum.unit:
            raise ValueError("range quantities must use the same unit")
        if self.minimum.value > self.maximum.value:
            raise ValueError("minimum cannot exceed maximum")
        return self


class BooleanAttributeValue(KnowledgeModel):
    kind: Literal["boolean"] = "boolean"
    value: bool


class TextAttributeValue(KnowledgeModel):
    kind: Literal["text"] = "text"
    value: str

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "attribute value")


class EnumAttributeValue(KnowledgeModel):
    kind: Literal["enum"] = "enum"
    value: str

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "attribute value")


ComponentAttributeValue = Annotated[
    QuantityExactValue
    | QuantityNominalValue
    | QuantityMinimumValue
    | QuantityMaximumValue
    | QuantityRangeValue
    | BooleanAttributeValue
    | TextAttributeValue
    | EnumAttributeValue,
    Field(discriminator="kind"),
]


class ComponentAttribute(KnowledgeModel):
    attribute_id: str
    name: str
    value: ComponentAttributeValue | None = None
    conditions: list[Condition] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    status: KnowledgeState = KnowledgeState.UNVERIFIED
    metadata: KnowledgeMetadata

    @field_validator("attribute_id")
    @classmethod
    def attribute_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "attribute_id")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "attribute name")

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "evidence_id") for item in value]
        return reject_duplicates(ids, "attribute evidence IDs")

    @model_validator(mode="after")
    def known_state_requires_value(self) -> "ComponentAttribute":
        if self.status in {KnowledgeState.VERIFIED, KnowledgeState.UNVERIFIED, KnowledgeState.CONFLICTING} and self.value is None:
            raise ValueError("known or conflicting attributes must include a value")
        return self


class KnowledgeSource(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    source_id: str
    source_type: KnowledgeSourceType
    title: str
    publisher_or_manufacturer: str | None = None
    document_identifier: str | None = None
    revision: str | None = None
    publication_date: date | None = None
    locator: str
    trust_class: SourceTrustClass
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    imported_by: str | None = None
    metadata: KnowledgeMetadata

    @field_validator("source_id")
    @classmethod
    def source_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "source_id")

    @field_validator("title", "locator")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "source text")

    @field_validator("publisher_or_manufacturer", "document_identifier", "revision", "imported_by")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "source optional text")

    @field_validator("imported_at")
    @classmethod
    def imported_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("imported_at must be timezone-aware")
        return value


class Evidence(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    evidence_id: str
    source_id: str
    locator: str
    extraction_method: ExtractionMethod
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_state: KnowledgeState
    validation_method: EvidenceValidationMethod | None = None
    metadata: KnowledgeMetadata

    @field_validator("evidence_id", "source_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "evidence id")

    @field_validator("locator")
    @classmethod
    def locator_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "evidence locator")

    @model_validator(mode="after")
    def llm_draft_cannot_self_verify(self) -> "Evidence":
        if self.extraction_method == ExtractionMethod.FUTURE_LLM_DRAFT and self.validation_state == KnowledgeState.VERIFIED:
            if self.validation_method is None or self.validation_method == EvidenceValidationMethod.NOT_VALIDATED:
                raise ValueError("verified future_llm_draft evidence requires independent validation_method")
        if self.validation_state == KnowledgeState.VERIFIED and self.validation_method is None:
            raise ValueError("verified evidence requires validation_method")
        return self


class ComplianceClaim(KnowledgeModel):
    claim_id: str
    standard: ComplianceStandard
    claim_type: ComplianceClaimType
    level: str | None = None
    scope: str | None = None
    evidence_state: KnowledgeState
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: KnowledgeMetadata

    @field_validator("claim_id")
    @classmethod
    def claim_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "claim_id")

    @field_validator("level", "scope")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "claim text")

    @field_validator("source_ids", "evidence_ids")
    @classmethod
    def refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "claim reference") for item in value]
        return reject_duplicates(ids, "claim references")


QualificationClaim = ComplianceClaim


class SymbolReference(KnowledgeModel):
    library: str
    symbol_name: str
    source_id: str
    verified_exists: bool
    metadata: KnowledgeMetadata

    @field_validator("library", "symbol_name")
    @classmethod
    def symbol_text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "symbol reference")

    @field_validator("source_id")
    @classmethod
    def source_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "source_id")


class FootprintReference(KnowledgeModel):
    library: str
    footprint_name: str
    package_mapping: str | None = None
    source_id: str
    verified_exists: bool
    metadata: KnowledgeMetadata

    @field_validator("library", "footprint_name")
    @classmethod
    def footprint_text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "footprint reference")

    @field_validator("package_mapping")
    @classmethod
    def package_mapping_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "package_mapping")

    @field_validator("source_id")
    @classmethod
    def source_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "source_id")


class ComponentRecord(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    component_id: str
    manufacturer: str
    part_number: str
    variant: str | None = None
    category: ComponentCategory
    description: str | None = None
    attributes: list[ComponentAttribute] = Field(default_factory=list)
    qualification_claims: list[ComplianceClaim] = Field(default_factory=list)
    compliance_claims: list[ComplianceClaim] = Field(default_factory=list)
    symbol_references: list[SymbolReference] = Field(default_factory=list)
    footprint_references: list[FootprintReference] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    documentation_status: DocumentationStatus
    lifecycle_status: LifecycleStatus = LifecycleStatus.UNKNOWN
    metadata: KnowledgeMetadata

    @field_validator("component_id")
    @classmethod
    def component_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "component_id")

    @field_validator("manufacturer", "part_number")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "component text")

    @field_validator("variant", "description")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "component optional text")

    @field_validator("source_ids")
    @classmethod
    def source_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "source_id") for item in value]
        return reject_duplicates(ids, "component source IDs")

    @model_validator(mode="before")
    @classmethod
    def selection_fields_are_forbidden(cls, data):
        if isinstance(data, dict):
            forbidden = sorted(_FORBIDDEN_COMPONENT_FIELDS & set(data))
            if forbidden:
                raise ValueError(f"ComponentRecord cannot contain selection fields: {', '.join(forbidden)}")
        return data

    @model_validator(mode="after")
    def component_refs_must_be_unique(self) -> "ComponentRecord":
        reject_duplicates([attribute.attribute_id for attribute in self.attributes], "attribute IDs")
        reject_duplicates(
            [claim.claim_id for claim in [*self.qualification_claims, *self.compliance_claims]],
            "claim IDs",
        )
        reject_duplicates(
            [f"{ref.library}:{ref.symbol_name}" for ref in self.symbol_references],
            "symbol references",
        )
        reject_duplicates(
            [f"{ref.library}:{ref.footprint_name}" for ref in self.footprint_references],
            "footprint references",
        )
        return self

    def identity(self) -> ComponentIdentity:
        return ComponentIdentity(manufacturer=self.manufacturer, part_number=self.part_number, variant=self.variant)


class ComplianceProfile(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    profile_id: str
    domain: ComplianceDomain | None = None
    required_standards: list[ComplianceStandard] = Field(default_factory=list)
    preferred_standards: list[ComplianceStandard] = Field(default_factory=list)
    required_qualifications: list[ComplianceStandard] = Field(default_factory=list)
    preferred_qualifications: list[ComplianceStandard] = Field(default_factory=list)
    metadata: KnowledgeMetadata

    @field_validator("profile_id")
    @classmethod
    def profile_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "profile_id")

    @field_validator("required_standards", "preferred_standards", "required_qualifications", "preferred_qualifications")
    @classmethod
    def standards_must_be_unique(cls, value: list[ComplianceStandard]) -> list[ComplianceStandard]:
        return reject_duplicates(value, "compliance profile standards")


class RuleApplicability(KnowledgeModel):
    component_category: ComponentCategory | None = None
    interface_type: str | None = None
    attribute_name: str | None = None
    notes: str | None = None

    @field_validator("interface_type", "attribute_name", "notes")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "rule applicability")


class EngineeringRule(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    rule_id: str
    category: EngineeringRuleCategory
    applicability: RuleApplicability = Field(default_factory=RuleApplicability)
    statement: str
    severity: EngineeringRuleSeverity
    source_ids: list[str] = Field(default_factory=list)
    status: EngineeringRuleStatus = EngineeringRuleStatus.ACTIVE
    metadata: KnowledgeMetadata

    @field_validator("rule_id")
    @classmethod
    def rule_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "rule_id")

    @field_validator("statement")
    @classmethod
    def statement_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "rule statement")

    @field_validator("source_ids")
    @classmethod
    def source_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "source_id") for item in value]
        return reject_duplicates(ids, "rule source IDs")


class SourceReference(KnowledgeModel):
    reference_type: SourceReferenceType
    locator: str

    @field_validator("locator")
    @classmethod
    def locator_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "source reference")


class KnowledgeImportRequest(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    import_request_id: str
    source_reference: SourceReference
    source_type: KnowledgeSourceType
    intended_component_identity: ComponentIdentity | None = None
    import_mode: KnowledgeImportMode = KnowledgeImportMode.CREATE_OR_ENRICH
    user_metadata: dict[str, str] = Field(default_factory=dict)
    metadata: KnowledgeMetadata

    @field_validator("import_request_id")
    @classmethod
    def import_request_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "import_request_id")


class KnowledgeImportConflict(KnowledgeModel):
    conflict_id: str
    component_id: str
    attribute_name: str
    existing_attribute_ids: list[str] = Field(default_factory=list)
    new_attribute_id: str | None = None
    description: str

    @field_validator("conflict_id", "component_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "conflict id")

    @field_validator("new_attribute_id")
    @classmethod
    def optional_new_attribute_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "new_attribute_id")

    @field_validator("existing_attribute_ids")
    @classmethod
    def existing_attribute_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "existing_attribute_id") for item in value]
        return reject_duplicates(ids, "existing attribute IDs")

    @field_validator("attribute_name", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "conflict text")


class KnowledgeImportResult(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    import_result_id: str
    status: KnowledgeImportStatus
    component_id: str | None = None
    created_component: bool = False
    updated_existing: bool = False
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[KnowledgeImportConflict] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    metadata: KnowledgeMetadata

    @field_validator("import_result_id")
    @classmethod
    def result_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "import_result_id")

    @field_validator("component_id")
    @classmethod
    def optional_component_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "component_id")

    @field_validator("source_ids")
    @classmethod
    def source_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "source_id") for item in value]
        return reject_duplicates(ids, "import result source IDs")

    @field_validator("warnings", "unresolved_fields")
    @classmethod
    def list_text_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return [require_nonblank(item, "import result text") for item in value]


class ManualKnowledgeEntry(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    manual_entry_id: str
    component_identity: ComponentIdentity | None = None
    component_id: str | None = None
    attribute_name: str
    value: ComponentAttributeValue | None = None
    note: str | None = None
    source_description: str | None = None
    evidence_state: KnowledgeState = KnowledgeState.UNVERIFIED
    source_trust: SourceTrustClass = SourceTrustClass.UNVERIFIED
    metadata: KnowledgeMetadata

    @field_validator("manual_entry_id")
    @classmethod
    def manual_entry_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "manual_entry_id")

    @field_validator("component_id")
    @classmethod
    def optional_component_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "component_id")

    @field_validator("attribute_name")
    @classmethod
    def attribute_name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "attribute_name")

    @field_validator("note", "source_description")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "manual entry text")

    @model_validator(mode="after")
    def component_reference_required(self) -> "ManualKnowledgeEntry":
        if self.component_identity is None and self.component_id is None:
            raise ValueError("manual entry requires component_identity or component_id")
        return self


class AttributeConstraint(KnowledgeModel):
    name: str
    required_value: ComponentAttributeValue

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "attribute constraint name")


class KnowledgeFilter(KnowledgeModel):
    category: ComponentCategory | None = None
    attribute_constraints: list[AttributeConstraint] = Field(default_factory=list)
    required_qualifications: list[ComplianceStandard] = Field(default_factory=list)
    preferred_qualifications: list[ComplianceStandard] = Field(default_factory=list)
    required_compliance: list[ComplianceStandard] = Field(default_factory=list)
    preferred_compliance: list[ComplianceStandard] = Field(default_factory=list)
    require_symbol: bool | None = None
    require_footprint: bool | None = None
    minimum_source_trust: SourceTrustClass | None = None
    documentation_statuses: list[DocumentationStatus] = Field(default_factory=list)

    @field_validator("required_qualifications", "preferred_qualifications", "required_compliance", "preferred_compliance")
    @classmethod
    def standards_must_be_unique(cls, value: list[ComplianceStandard]) -> list[ComplianceStandard]:
        return reject_duplicates(value, "filter standards")

    @field_validator("documentation_statuses")
    @classmethod
    def statuses_must_be_unique(cls, value: list[DocumentationStatus]) -> list[DocumentationStatus]:
        return reject_duplicates(value, "documentation statuses")


class KnowledgeQuery(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    query_id: str
    filters: KnowledgeFilter = Field(default_factory=KnowledgeFilter)
    include_rules: bool = True
    metadata: KnowledgeMetadata

    @field_validator("query_id")
    @classmethod
    def query_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "query_id")


class UnresolvedKnowledge(KnowledgeModel):
    item_id: str
    component_id: str | None = None
    topic: str
    state: KnowledgeState = KnowledgeState.UNKNOWN
    description: str

    @field_validator("item_id")
    @classmethod
    def item_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "unresolved item id")

    @field_validator("component_id")
    @classmethod
    def optional_component_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "component_id")

    @field_validator("topic", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "unresolved knowledge text")


class KnowledgeContext(KnowledgeModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    context_id: str
    query: KnowledgeQuery
    component_records: list[ComponentRecord] = Field(default_factory=list)
    engineering_rules: list[EngineeringRule] = Field(default_factory=list)
    sources: list[KnowledgeSource] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    applied_filters: list[str] = Field(default_factory=list)
    unresolved_knowledge: list[UnresolvedKnowledge] = Field(default_factory=list)
    conflicts: list[KnowledgeImportConflict] = Field(default_factory=list)
    metadata: KnowledgeMetadata

    @field_validator("context_id")
    @classmethod
    def context_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "context_id")

    @field_validator("source_ids", "applied_filters")
    @classmethod
    def refs_and_filters_must_be_valid(cls, value: list[str]) -> list[str]:
        return reject_duplicates([require_nonblank(item, "context item") for item in value], "context values")

    @model_validator(mode="before")
    @classmethod
    def derive_source_ids_from_sources(cls, data):
        if isinstance(data, dict) and "source_ids" not in data:
            sources = data.get("sources", [])
            data = dict(data)
            data["source_ids"] = sorted(source_id_from_source(source) for source in sources)
        return data

    @model_validator(mode="after")
    def provenance_ids_must_be_consistent(self) -> "KnowledgeContext":
        source_ids = [source.source_id for source in self.sources]
        reject_duplicates(source_ids, "context sources")
        evidence_ids = [item.evidence_id for item in self.evidence]
        reject_duplicates(evidence_ids, "context evidence")
        if sorted(self.source_ids) != sorted(source_ids):
            raise ValueError("source_ids must match sources in KnowledgeContext")
        known_sources = set(source_ids)
        known_evidence = set(evidence_ids)
        for item in self.evidence:
            if item.source_id not in known_sources:
                raise ValueError(f"{item.evidence_id} references source outside KnowledgeContext: {item.source_id}")
        for component in self.component_records:
            for source_id in component.source_ids:
                if source_id not in known_sources:
                    raise ValueError(f"{component.component_id} references source outside KnowledgeContext: {source_id}")
            for attribute in component.attributes:
                for evidence_id in attribute.evidence_ids:
                    if evidence_id not in known_evidence:
                        raise ValueError(f"{attribute.attribute_id} references evidence outside KnowledgeContext: {evidence_id}")
            for claim in [*component.qualification_claims, *component.compliance_claims]:
                for source_id in claim.source_ids:
                    if source_id not in known_sources:
                        raise ValueError(f"{claim.claim_id} references source outside KnowledgeContext: {source_id}")
                for evidence_id in claim.evidence_ids:
                    if evidence_id not in known_evidence:
                        raise ValueError(f"{claim.claim_id} references evidence outside KnowledgeContext: {evidence_id}")
            for reference in [*component.symbol_references, *component.footprint_references]:
                if reference.source_id not in known_sources:
                    raise ValueError(f"CAD reference points to source outside KnowledgeContext: {reference.source_id}")
        for rule in self.engineering_rules:
            for source_id in rule.source_ids:
                if source_id not in known_sources:
                    raise ValueError(f"{rule.rule_id} references source outside KnowledgeContext: {source_id}")
        return self


def deterministic_component_id(identity: ComponentIdentity) -> str:
    tokens = [identity.manufacturer, identity.part_number]
    if identity.variant:
        tokens.append(identity.variant)
    normalized = "_".join(canonical_identity_text(token) for token in tokens)
    cleaned = "".join(character if character.isalnum() else "_" for character in normalized).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return f"CMP_{cleaned.upper()}"


def canonical_identity_text(value: str) -> str:
    return require_nonblank(value, "identity").strip().casefold()


def quantity(value: float, unit: str) -> Quantity:
    return Quantity(value=require_finite_number(value, "quantity"), unit=require_nonblank(unit, "unit"))


def source_id_from_source(source) -> str:
    if isinstance(source, KnowledgeSource):
        return source.source_id
    if isinstance(source, dict):
        return source.get("source_id", "")
    return ""
