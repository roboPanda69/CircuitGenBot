"""Deterministic in-memory repository for Engineering Knowledge v0.1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from schematic_ai.domain.knowledge import (
    AttributeConstraint,
    ComponentAttribute,
    ComponentIdentity,
    ComponentRecord,
    ComplianceClaim,
    ComplianceStandard,
    EngineeringRule,
    KnowledgeContext,
    KnowledgeFilter,
    KnowledgeImportConflict,
    KnowledgeImportResult,
    KnowledgeImportStatus,
    KnowledgeMetadata,
    KnowledgeQuery,
    KnowledgeSource,
    KnowledgeState,
    ManualKnowledgeEntry,
    QuantityExactValue,
    QuantityMaximumValue,
    QuantityMinimumValue,
    QuantityNominalValue,
    QuantityRangeValue,
    SymbolReference,
    FootprintReference,
    UnresolvedKnowledge,
    deterministic_component_id,
)
from schematic_ai.domain.knowledge.enums import SourceTrustClass
from schematic_ai.domain.knowledge.models import Evidence


class KnowledgeRepositoryError(ValueError):
    """Raised when repository invariants would be violated."""


_TRUST_ORDER = {
    SourceTrustClass.UNVERIFIED: 0,
    SourceTrustClass.INFERRED: 1,
    SourceTrustClass.CURATED_INTERNAL: 2,
    SourceTrustClass.TRUSTED_SECONDARY: 3,
    SourceTrustClass.AUTHORITATIVE: 4,
}


@dataclass
class InMemoryKnowledgeRepository:
    components: dict[str, ComponentRecord] = field(default_factory=dict)
    sources: dict[str, KnowledgeSource] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    rules: dict[str, EngineeringRule] = field(default_factory=dict)
    conflicts: list[KnowledgeImportConflict] = field(default_factory=list)

    def add_source(self, source: KnowledgeSource) -> KnowledgeSource:
        if source.source_id in self.sources:
            raise KnowledgeRepositoryError(f"duplicate source_id: {source.source_id}")
        self.sources[source.source_id] = deepcopy(source)
        return deepcopy(source)

    def add_evidence(self, evidence: Evidence) -> Evidence:
        if evidence.evidence_id in self.evidence:
            raise KnowledgeRepositoryError(f"duplicate evidence_id: {evidence.evidence_id}")
        if evidence.source_id not in self.sources:
            raise KnowledgeRepositoryError(f"{evidence.evidence_id} references unknown source {evidence.source_id}")
        self.evidence[evidence.evidence_id] = deepcopy(evidence)
        return deepcopy(evidence)

    def add_rule(self, rule: EngineeringRule) -> EngineeringRule:
        if rule.rule_id in self.rules:
            raise KnowledgeRepositoryError(f"duplicate rule_id: {rule.rule_id}")
        self._validate_source_refs(rule.source_ids, f"rule {rule.rule_id}")
        self.rules[rule.rule_id] = deepcopy(rule)
        return deepcopy(rule)

    def add_component(self, component: ComponentRecord) -> ComponentRecord:
        if component.component_id in self.components:
            raise KnowledgeRepositoryError(f"duplicate component_id: {component.component_id}")
        if self.find_component_by_identity(component.identity()) is not None:
            raise KnowledgeRepositoryError(f"duplicate component identity: {component.manufacturer} {component.part_number}")
        self._validate_component_refs(component)
        self.components[component.component_id] = deepcopy(component)
        return deepcopy(component)

    def get_component(self, component_id: str) -> ComponentRecord | None:
        component = self.components.get(component_id)
        return deepcopy(component) if component is not None else None

    def find_component_by_identity(self, identity: ComponentIdentity) -> ComponentRecord | None:
        key = identity.canonical_key()
        for component in self.components.values():
            if component.identity().canonical_key() == key:
                return deepcopy(component)
        return None

    def upsert_component(self, component: ComponentRecord, *, result_id: str = "KIR_001") -> KnowledgeImportResult:
        existing = self.find_component_by_identity(component.identity())
        if existing is None:
            self.add_component(component)
            return KnowledgeImportResult(
                import_result_id=result_id,
                status=KnowledgeImportStatus.CREATED,
                component_id=component.component_id,
                created_component=True,
                source_ids=component.source_ids,
                metadata=metadata("knowledge_repository"),
            )

        if component_is_duplicate(existing, component):
            return KnowledgeImportResult(
                import_result_id=result_id,
                status=KnowledgeImportStatus.DUPLICATE,
                component_id=existing.component_id,
                source_ids=existing.source_ids,
                metadata=metadata("knowledge_repository"),
            )

        merged, conflicts = self._merge_component(existing, component)
        self.components[existing.component_id] = merged
        self.conflicts.extend(conflicts)
        return KnowledgeImportResult(
            import_result_id=result_id,
            status=KnowledgeImportStatus.NEEDS_REVIEW if conflicts else KnowledgeImportStatus.UPDATED_EXISTING,
            component_id=existing.component_id,
            updated_existing=True,
            source_ids=merged.source_ids,
            conflicts=conflicts,
            warnings=["conflicting knowledge preserved for review"] if conflicts else [],
            metadata=metadata("knowledge_repository"),
        )

    def apply_manual_entry(
        self,
        entry: ManualKnowledgeEntry,
        *,
        category=None,
        result_id: str = "KIR_MANUAL_001",
    ) -> KnowledgeImportResult:
        component = self._component_for_manual_entry(entry, category)
        source_id = f"SRC_{entry.manual_entry_id}"
        evidence_id = f"EVID_{entry.manual_entry_id}"
        if source_id not in self.sources:
            self.add_source(
                KnowledgeSource(
                    source_id=source_id,
                    source_type="manual_entry",
                    title=entry.source_description or f"Manual entry {entry.manual_entry_id}",
                    locator=entry.note or entry.manual_entry_id,
                    trust_class=entry.source_trust,
                    metadata=metadata("manual_entry"),
                )
            )
        if evidence_id not in self.evidence:
            self.add_evidence(
                Evidence(
                    evidence_id=evidence_id,
                    source_id=source_id,
                    locator=entry.note or entry.manual_entry_id,
                    extraction_method="manual",
                    extraction_confidence=None,
                    validation_state=entry.evidence_state,
                    validation_method="manual_review" if entry.evidence_state == KnowledgeState.VERIFIED else "not_validated",
                    metadata=metadata("manual_entry"),
                )
            )
        attribute = ComponentAttribute(
            attribute_id=self._next_attribute_id(component),
            name=entry.attribute_name,
            value=entry.value,
            evidence_ids=[evidence_id],
            status=entry.evidence_state,
            metadata=metadata("manual_entry"),
        )
        data = component.model_dump(mode="json")
        data["source_ids"] = sorted(set([*component.source_ids, source_id]))
        data["attributes"].append(attribute.model_dump(mode="json"))
        updated = ComponentRecord.model_validate(data)
        return self.upsert_component(updated, result_id=result_id)

    def add_symbol_reference(self, component_id: str, reference: SymbolReference) -> ComponentRecord:
        return self._add_component_reference(component_id, reference, "symbol_references")

    def add_footprint_reference(self, component_id: str, reference: FootprintReference) -> ComponentRecord:
        return self._add_component_reference(component_id, reference, "footprint_references")

    def query(self, query: KnowledgeQuery) -> KnowledgeContext:
        filters = query.filters
        matched: list[ComponentRecord] = []
        applied_filters = describe_filters(filters)
        unresolved: list[UnresolvedKnowledge] = []
        context_conflicts: list[KnowledgeImportConflict] = []

        for component in self.components.values():
            if not self._component_matches(component, filters):
                continue
            matched.append(deepcopy(component))
            unresolved.extend(unresolved_for_component(component, filters))
            context_conflicts.extend(conflict for conflict in self.conflicts if conflict.component_id == component.component_id)

        rules = self._matching_rules(filters) if query.include_rules else []
        sources, evidence_items = self._provenance_closure(matched, rules)
        return KnowledgeContext(
            context_id=f"KCTX_{query.query_id}",
            query=query,
            component_records=matched,
            engineering_rules=rules,
            sources=sources,
            evidence=evidence_items,
            applied_filters=applied_filters,
            unresolved_knowledge=unresolved,
            conflicts=context_conflicts,
            metadata=metadata("knowledge_repository"),
        )

    def _validate_component_refs(self, component: ComponentRecord) -> None:
        self._validate_source_refs(component.source_ids, f"component {component.component_id}")
        known_evidence = set(self.evidence)
        known_sources = set(self.sources)
        for attribute in component.attributes:
            for evidence_id in attribute.evidence_ids:
                if evidence_id not in known_evidence:
                    raise KnowledgeRepositoryError(f"{attribute.attribute_id} references unknown evidence {evidence_id}")
        for claim in [*component.qualification_claims, *component.compliance_claims]:
            self._validate_claim_refs(claim, known_sources, known_evidence)
        for reference in [*component.symbol_references, *component.footprint_references]:
            if reference.source_id not in known_sources:
                raise KnowledgeRepositoryError(f"CAD reference points to unknown source {reference.source_id}")

    def _validate_claim_refs(self, claim: ComplianceClaim, known_sources: set[str], known_evidence: set[str]) -> None:
        for source_id in claim.source_ids:
            if source_id not in known_sources:
                raise KnowledgeRepositoryError(f"{claim.claim_id} references unknown source {source_id}")
        for evidence_id in claim.evidence_ids:
            if evidence_id not in known_evidence:
                raise KnowledgeRepositoryError(f"{claim.claim_id} references unknown evidence {evidence_id}")

    def _validate_source_refs(self, source_ids: list[str], owner: str) -> None:
        for source_id in source_ids:
            if source_id not in self.sources:
                raise KnowledgeRepositoryError(f"{owner} references unknown source {source_id}")

    def _merge_component(
        self,
        existing: ComponentRecord,
        incoming: ComponentRecord,
    ) -> tuple[ComponentRecord, list[KnowledgeImportConflict]]:
        self._validate_component_refs(incoming)
        data = existing.model_dump(mode="json")
        data["source_ids"] = sorted(set([*existing.source_ids, *incoming.source_ids]))
        data["symbol_references"] = merge_by_key(
            data["symbol_references"],
            [item.model_dump(mode="json") for item in incoming.symbol_references],
            ("library", "symbol_name"),
        )
        data["footprint_references"] = merge_by_key(
            data["footprint_references"],
            [item.model_dump(mode="json") for item in incoming.footprint_references],
            ("library", "footprint_name"),
        )
        conflicts: list[KnowledgeImportConflict] = []
        existing_by_name = {}
        used_attribute_ids = {attribute["attribute_id"] for attribute in data["attributes"]}
        for attribute in data["attributes"]:
            existing_by_name.setdefault(attribute["name"], []).append(attribute)
        for attribute in incoming.attributes:
            attr_data = attribute.model_dump(mode="json")
            if attr_data["attribute_id"] in used_attribute_ids:
                attr_data["attribute_id"] = next_sequential_id("ATTR", used_attribute_ids)
            used_attribute_ids.add(attr_data["attribute_id"])
            matches = existing_by_name.get(attribute.name, [])
            if any(attribute_values_equal(match["value"], attr_data["value"]) for match in matches):
                for match in matches:
                    if attribute_values_equal(match["value"], attr_data["value"]):
                        match["evidence_ids"] = sorted(set([*match["evidence_ids"], *attr_data["evidence_ids"]]))
                        break
            else:
                attr_data["status"] = KnowledgeState.CONFLICTING.value if matches else attr_data["status"]
                data["attributes"].append(attr_data)
                if matches:
                    conflicts.append(
                        KnowledgeImportConflict(
                            conflict_id=f"KCONF_{len(self.conflicts) + len(conflicts) + 1:03d}",
                            component_id=existing.component_id,
                            attribute_name=attribute.name,
                            existing_attribute_ids=[match["attribute_id"] for match in matches],
                            new_attribute_id=attr_data["attribute_id"],
                            description=f"Conflicting values for {attribute.name} were preserved.",
                        )
                    )
        used_claim_ids = {
            claim["claim_id"]
            for claim in [*data["qualification_claims"], *data["compliance_claims"]]
        }
        data["qualification_claims"], qualification_conflicts = merge_claims(
            data["qualification_claims"],
            incoming.qualification_claims,
            existing.component_id,
            used_claim_ids,
            len(self.conflicts) + len(conflicts),
        )
        conflicts.extend(qualification_conflicts)
        data["compliance_claims"], compliance_conflicts = merge_claims(
            data["compliance_claims"],
            incoming.compliance_claims,
            existing.component_id,
            used_claim_ids,
            len(self.conflicts) + len(conflicts),
        )
        conflicts.extend(compliance_conflicts)
        data["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
        return ComponentRecord.model_validate(data), conflicts

    def _component_matches(self, component: ComponentRecord, filters: KnowledgeFilter) -> bool:
        if filters.category is not None and component.category != filters.category:
            return False
        if filters.documentation_statuses and component.documentation_status not in filters.documentation_statuses:
            return False
        if filters.require_symbol is True and not any(ref.verified_exists for ref in component.symbol_references):
            return False
        if filters.require_footprint is True and not any(ref.verified_exists for ref in component.footprint_references):
            return False
        if filters.minimum_source_trust is not None and not self._has_minimum_trust(component, filters.minimum_source_trust):
            return False
        if not all(component_has_claim(component.qualification_claims, standard) for standard in filters.required_qualifications):
            return False
        if not all(component_has_claim(component.compliance_claims, standard) for standard in filters.required_compliance):
            return False
        if not all(component_satisfies_attribute(component, constraint) for constraint in filters.attribute_constraints):
            return False
        return True

    def _has_minimum_trust(self, component: ComponentRecord, minimum: SourceTrustClass) -> bool:
        minimum_value = _TRUST_ORDER[minimum]
        return any(_TRUST_ORDER[self.sources[source_id].trust_class] >= minimum_value for source_id in component.source_ids if source_id in self.sources)

    def _matching_rules(self, filters: KnowledgeFilter) -> list[EngineeringRule]:
        result = []
        for rule in self.rules.values():
            if filters.category is not None and rule.applicability.component_category not in {None, filters.category}:
                continue
            result.append(deepcopy(rule))
        return result

    def _provenance_closure(
        self,
        components: list[ComponentRecord],
        rules: list[EngineeringRule],
    ) -> tuple[list[KnowledgeSource], list[Evidence]]:
        source_ids: set[str] = set()
        evidence_ids: set[str] = set()
        for component in components:
            source_ids.update(component.source_ids)
            for attribute in component.attributes:
                evidence_ids.update(attribute.evidence_ids)
            for claim in [*component.qualification_claims, *component.compliance_claims]:
                source_ids.update(claim.source_ids)
                evidence_ids.update(claim.evidence_ids)
            for reference in [*component.symbol_references, *component.footprint_references]:
                source_ids.add(reference.source_id)
        for rule in rules:
            source_ids.update(rule.source_ids)
        evidence_items = []
        for evidence_id in sorted(evidence_ids):
            try:
                item = self.evidence[evidence_id]
            except KeyError as exc:
                raise KnowledgeRepositoryError(f"KnowledgeContext cannot close missing evidence {evidence_id}") from exc
            evidence_items.append(deepcopy(item))
            source_ids.add(item.source_id)
        source_items = []
        for source_id in sorted(source_ids):
            try:
                source = self.sources[source_id]
            except KeyError as exc:
                raise KnowledgeRepositoryError(f"KnowledgeContext cannot close missing source {source_id}") from exc
            source_items.append(deepcopy(source))
        return source_items, evidence_items

    def _component_for_manual_entry(self, entry: ManualKnowledgeEntry, category) -> ComponentRecord:
        if entry.component_id is not None:
            component = self.get_component(entry.component_id)
            if component is None:
                raise KnowledgeRepositoryError(f"unknown component_id: {entry.component_id}")
            return component
        assert entry.component_identity is not None
        existing = self.find_component_by_identity(entry.component_identity)
        if existing is not None:
            return existing
        if category is None:
            category = "other"
        return ComponentRecord(
            component_id=deterministic_component_id(entry.component_identity),
            manufacturer=entry.component_identity.manufacturer,
            part_number=entry.component_identity.part_number,
            variant=entry.component_identity.variant,
            category=category,
            documentation_status="user_supplied_only",
            metadata=metadata("manual_entry"),
        )

    def _next_attribute_id(self, component: ComponentRecord) -> str:
        return f"ATTR_{len(component.attributes) + 1:03d}"

    def _add_component_reference(self, component_id: str, reference, collection_name: str) -> ComponentRecord:
        if reference.source_id not in self.sources:
            raise KnowledgeRepositoryError(f"CAD reference points to unknown source {reference.source_id}")
        component = self.get_component(component_id)
        if component is None:
            raise KnowledgeRepositoryError(f"unknown component_id: {component_id}")
        data = component.model_dump(mode="json")
        data[collection_name].append(reference.model_dump(mode="json"))
        updated = ComponentRecord.model_validate(data)
        self.components[component_id] = updated
        return deepcopy(updated)


def metadata(created_by: str) -> KnowledgeMetadata:
    return KnowledgeMetadata(created_by=created_by)


def merge_by_key(existing: list[dict], incoming: list[dict], keys: tuple[str, ...]) -> list[dict]:
    result = deepcopy(existing)
    known = {tuple(item.get(key) for key in keys) for item in result}
    for item in incoming:
        key = tuple(item.get(key) for key in keys)
        if key not in known:
            result.append(deepcopy(item))
            known.add(key)
    return result


def next_sequential_id(prefix: str, used_ids: set[str]) -> str:
    counter = 1
    while f"{prefix}_{counter:03d}" in used_ids:
        counter += 1
    return f"{prefix}_{counter:03d}"


def merge_claims(
    existing_claims: list[dict],
    incoming_claims: list[ComplianceClaim],
    component_id: str,
    used_claim_ids: set[str],
    conflict_offset: int,
) -> tuple[list[dict], list[KnowledgeImportConflict]]:
    result = deepcopy(existing_claims)
    conflicts: list[KnowledgeImportConflict] = []
    for incoming in incoming_claims:
        incoming_data = incoming.model_dump(mode="json")
        exact_match = next(
            (
                claim
                for claim in result
                if claim_subject_key(claim) == claim_subject_key(incoming_data)
                and claim_state_key(claim) == claim_state_key(incoming_data)
            ),
            None,
        )
        if exact_match is not None:
            exact_match["source_ids"] = sorted(set([*exact_match["source_ids"], *incoming_data["source_ids"]]))
            exact_match["evidence_ids"] = sorted(set([*exact_match["evidence_ids"], *incoming_data["evidence_ids"]]))
            continue

        same_subject = [claim for claim in result if claim_subject_key(claim) == claim_subject_key(incoming_data)]
        if incoming_data["claim_id"] in used_claim_ids:
            incoming_data["claim_id"] = next_sequential_id("CLAIM", used_claim_ids)
        used_claim_ids.add(incoming_data["claim_id"])
        result.append(incoming_data)
        if any(conflicting_claim_states(claim["evidence_state"], incoming_data["evidence_state"]) for claim in same_subject):
            conflicts.append(
                KnowledgeImportConflict(
                    conflict_id=f"KCONF_{conflict_offset + len(conflicts) + 1:03d}",
                    component_id=component_id,
                    attribute_name=f"claim:{incoming_data['standard']}:{incoming_data['claim_type']}",
                    existing_attribute_ids=[claim["claim_id"] for claim in same_subject],
                    new_attribute_id=incoming_data["claim_id"],
                    description=f"Conflicting claim evidence for {incoming_data['standard']} was preserved.",
                )
            )
    return result, conflicts


def claim_subject_key(claim: dict) -> tuple:
    return (claim["standard"], claim["claim_type"], claim.get("level"), claim.get("scope"))


def claim_state_key(claim: dict) -> tuple:
    return (
        claim["evidence_state"],
        tuple(sorted(claim.get("source_ids", []))),
        tuple(sorted(claim.get("evidence_ids", []))),
    )


def conflicting_claim_states(existing_state: str, incoming_state: str) -> bool:
    return {existing_state, incoming_state} == {KnowledgeState.VERIFIED.value, KnowledgeState.VERIFIED_NO.value}


def attribute_values_equal(left, right) -> bool:
    return left == right


def component_is_duplicate(existing: ComponentRecord, incoming: ComponentRecord) -> bool:
    if not set(incoming.source_ids).issubset(set(existing.source_ids)):
        return False
    if not references_subset(
        [item.model_dump(mode="json") for item in incoming.symbol_references],
        [item.model_dump(mode="json") for item in existing.symbol_references],
        ("library", "symbol_name"),
    ):
        return False
    if not references_subset(
        [item.model_dump(mode="json") for item in incoming.footprint_references],
        [item.model_dump(mode="json") for item in existing.footprint_references],
        ("library", "footprint_name"),
    ):
        return False
    if not claims_subset(incoming.qualification_claims, existing.qualification_claims):
        return False
    if not claims_subset(incoming.compliance_claims, existing.compliance_claims):
        return False
    return all(attribute_has_duplicate(attribute, existing.attributes) for attribute in incoming.attributes)


def references_subset(incoming: list[dict], existing: list[dict], keys: tuple[str, ...]) -> bool:
    existing_keys = {tuple(item.get(key) for key in keys) for item in existing}
    return all(tuple(item.get(key) for key in keys) in existing_keys for item in incoming)


def claims_subset(incoming: list[ComplianceClaim], existing: list[ComplianceClaim]) -> bool:
    existing_keys = {
        (
            claim.standard,
            claim.claim_type,
            claim.level,
            claim.scope,
            claim.evidence_state,
            tuple(sorted(claim.source_ids)),
            tuple(sorted(claim.evidence_ids)),
        )
        for claim in existing
    }
    return all(
        (
            claim.standard,
            claim.claim_type,
            claim.level,
            claim.scope,
            claim.evidence_state,
            tuple(sorted(claim.source_ids)),
            tuple(sorted(claim.evidence_ids)),
        )
        in existing_keys
        for claim in incoming
    )


def attribute_has_duplicate(incoming: ComponentAttribute, existing_attributes: list[ComponentAttribute]) -> bool:
    incoming_evidence = set(incoming.evidence_ids)
    for existing in existing_attributes:
        if existing.name != incoming.name:
            continue
        if existing.status != incoming.status:
            continue
        if not attribute_values_equal(
            existing.value.model_dump(mode="json") if existing.value is not None else None,
            incoming.value.model_dump(mode="json") if incoming.value is not None else None,
        ):
            continue
        if incoming_evidence.issubset(set(existing.evidence_ids)):
            return True
    return False


def component_has_claim(claims: list[ComplianceClaim], standard: ComplianceStandard) -> bool:
    return any(claim.standard == standard and claim.evidence_state == KnowledgeState.VERIFIED for claim in claims)


def component_satisfies_attribute(component: ComponentRecord, constraint: AttributeConstraint) -> bool:
    for attribute in component.attributes:
        if attribute.name != constraint.name or attribute.status != KnowledgeState.VERIFIED or attribute.value is None:
            continue
        if value_satisfies(attribute.value, constraint.required_value):
            return True
    return False


def value_satisfies(known, required) -> bool:
    if isinstance(required, (QuantityExactValue, QuantityNominalValue)):
        return quantity_interval_contains(attribute_interval(known), required.value.value, required.value.unit)
    if isinstance(required, QuantityMinimumValue):
        interval = attribute_interval(known)
        return interval is not None and interval[1] >= required.value.value and interval[2] == required.value.unit
    if isinstance(required, QuantityMaximumValue):
        interval = attribute_interval(known)
        return interval is not None and interval[0] <= required.value.value and interval[2] == required.value.unit
    return known == required


def attribute_interval(value) -> tuple[float, float, str] | None:
    if isinstance(value, (QuantityExactValue, QuantityNominalValue)):
        return (value.value.value, value.value.value, value.value.unit)
    if isinstance(value, QuantityRangeValue):
        return (value.minimum.value, value.maximum.value, value.minimum.unit)
    if isinstance(value, QuantityMinimumValue):
        return (value.value.value, float("inf"), value.value.unit)
    if isinstance(value, QuantityMaximumValue):
        return (float("-inf"), value.value.value, value.value.unit)
    return None


def quantity_interval_contains(interval: tuple[float, float, str] | None, value: float, unit: str) -> bool:
    if interval is None:
        return False
    minimum, maximum, interval_unit = interval
    return interval_unit == unit and minimum <= value <= maximum


def unresolved_for_component(component: ComponentRecord, filters: KnowledgeFilter) -> list[UnresolvedKnowledge]:
    unresolved = []
    for standard in [*filters.preferred_qualifications, *filters.preferred_compliance]:
        claims = [*component.qualification_claims, *component.compliance_claims]
        if not any(claim.standard == standard and claim.evidence_state == KnowledgeState.VERIFIED for claim in claims):
            unresolved.append(
                UnresolvedKnowledge(
                    item_id=f"UNK_{component.component_id}_{standard}".replace("-", "_"),
                    component_id=component.component_id,
                    topic=str(standard),
                    state=KnowledgeState.UNKNOWN,
                    description=f"No verified evidence is present for preferred {standard}.",
                )
            )
    return unresolved


def describe_filters(filters: KnowledgeFilter) -> list[str]:
    result = []
    if filters.category is not None:
        result.append(f"category={filters.category}")
    for standard in filters.required_qualifications:
        result.append(f"required_qualification={standard}")
    for standard in filters.required_compliance:
        result.append(f"required_compliance={standard}")
    for standard in filters.preferred_qualifications:
        result.append(f"preferred_qualification={standard}")
    for standard in filters.preferred_compliance:
        result.append(f"preferred_compliance={standard}")
    if filters.require_symbol:
        result.append("require_symbol=true")
    if filters.require_footprint:
        result.append("require_footprint=true")
    if filters.minimum_source_trust is not None:
        result.append(f"minimum_source_trust={filters.minimum_source_trust}")
    for constraint in filters.attribute_constraints:
        result.append(f"attribute={constraint.name}")
    return result
