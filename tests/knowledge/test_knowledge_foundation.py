import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from schematic_ai.application.knowledge import (
    InMemoryKnowledgeRepository,
    KnowledgeRepositoryError,
    footprint_reference_if_exists,
    index_kicad_footprints,
    index_kicad_symbols,
    kicad_library_source,
    symbol_reference_if_exists,
)
from schematic_ai.domain.knowledge import (
    AttributeConstraint,
    ComponentAttribute,
    ComponentIdentity,
    ComponentRecord,
    ComplianceClaim,
    ComplianceProfile,
    EngineeringRule,
    Evidence,
    KnowledgeFilter,
    KnowledgeImportStatus,
    KnowledgeMetadata,
    KnowledgeQuery,
    KnowledgeSource,
    KnowledgeState,
    ManualKnowledgeEntry,
    QuantityExactValue,
    QuantityMaximumValue,
    QuantityRangeValue,
    RuleApplicability,
    deterministic_component_id,
    quantity,
)


def metadata():
    return KnowledgeMetadata(created_by="unit_test")


def source(source_id="SRC_DS_001", trust="authoritative"):
    return KnowledgeSource(
        source_id=source_id,
        source_type="manufacturer_datasheet",
        title="Synthetic Power Converter Datasheet",
        publisher_or_manufacturer="Synthetic Semiconductor",
        document_identifier="SYN-PWR-001-DS",
        revision="A",
        locator="tests/fixtures/synthetic_power_converter.pdf",
        trust_class=trust,
        metadata=metadata(),
    )


def evidence(evidence_id="EVID_DS_001", source_id="SRC_DS_001"):
    return Evidence(
        evidence_id=evidence_id,
        source_id=source_id,
        locator="page 12 electrical characteristics",
        extraction_method="manual",
        extraction_confidence=1.0,
        validation_state="verified",
        validation_method="manual_review",
        metadata=metadata(),
    )


def llm_evidence(evidence_id="EVID_LLM_001", source_id="SRC_DS_001", state="unverified", validation_method=None):
    return Evidence(
        evidence_id=evidence_id,
        source_id=source_id,
        locator="page 12 electrical characteristics",
        extraction_method="future_llm_draft",
        extraction_confidence=0.8,
        validation_state=state,
        validation_method=validation_method,
        metadata=metadata(),
    )


def input_voltage_attribute(value_min=3, value_max=17, evidence_id="EVID_DS_001", attribute_id="ATTR_001"):
    return ComponentAttribute(
        attribute_id=attribute_id,
        name="input_voltage",
        value=QuantityRangeValue(
            minimum=quantity(value_min, "V"),
            maximum=quantity(value_max, "V"),
        ),
        evidence_ids=[evidence_id],
        status="verified",
        metadata=metadata(),
    )


def max_current_attribute(value=3, evidence_id="EVID_DS_001", attribute_id="ATTR_002"):
    return ComponentAttribute(
        attribute_id=attribute_id,
        name="maximum_output_current",
        value=QuantityMaximumValue(value=quantity(value, "A")),
        evidence_ids=[evidence_id],
        status="verified",
        metadata=metadata(),
    )


def claim(claim_id, standard, state="verified", source_id="SRC_DS_001", evidence_id="EVID_DS_001", claim_type="qualified_to"):
    return ComplianceClaim(
        claim_id=claim_id,
        standard=standard,
        claim_type=claim_type,
        level=None,
        scope="synthetic component fixture",
        evidence_state=state,
        source_ids=[source_id],
        evidence_ids=[evidence_id],
        metadata=metadata(),
    )


def component(
    component_id="CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001",
    part_number="SYN-PWR-001",
    source_id="SRC_DS_001",
    evidence_id="EVID_DS_001",
    claims=None,
    compliance_claims=None,
):
    identity = ComponentIdentity(manufacturer="Synthetic Semiconductor", part_number=part_number)
    return ComponentRecord(
        component_id=component_id,
        manufacturer=identity.manufacturer,
        part_number=identity.part_number,
        category="power_converter",
        description="Synthetic switching converter fixture.",
        attributes=[
            input_voltage_attribute(evidence_id=evidence_id),
            max_current_attribute(evidence_id=evidence_id),
        ],
        qualification_claims=claims if claims is not None else [claim("CLAIM_AEC_001", "AEC_Q100", source_id=source_id, evidence_id=evidence_id)],
        compliance_claims=compliance_claims if compliance_claims is not None else [],
        source_ids=[source_id],
        documentation_status="complete",
        lifecycle_status="active",
        metadata=metadata(),
    )


def repository_with_component(record=None):
    repo = InMemoryKnowledgeRepository()
    repo.add_source(source())
    repo.add_evidence(evidence())
    repo.add_component(record or component())
    return repo


class KnowledgeModelTests(unittest.TestCase):
    def test_component_record_serializes_and_rejects_selection_fields(self):
        record = component()
        restored = ComponentRecord.model_validate_json(record.model_dump_json())

        self.assertEqual(restored.model_dump(mode="json"), record.model_dump(mode="json"))
        data = record.model_dump(mode="json")
        data["selected_for_design"] = True
        with self.assertRaises(ValidationError):
            ComponentRecord.model_validate(data)

    def test_component_record_rejects_duplicate_attributes_and_claims(self):
        data = component().model_dump(mode="json")
        data["attributes"].append(data["attributes"][0])
        with self.assertRaises(ValidationError):
            ComponentRecord.model_validate(data)

        data = component().model_dump(mode="json")
        data["compliance_claims"].append(data["qualification_claims"][0])
        with self.assertRaises(ValidationError):
            ComponentRecord.model_validate(data)

    def test_deterministic_component_id_uses_factual_identity(self):
        identity = ComponentIdentity(manufacturer="Synthetic Semiconductor", part_number="SYN-PWR-001", variant="Tape Reel")

        self.assertEqual(
            deterministic_component_id(identity),
            "CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001_TAPE_REEL",
        )

    def test_documentation_missing_does_not_make_component_invalid(self):
        record = ComponentRecord(
            component_id="CMP_UNKNOWN_001",
            manufacturer="Unknown Maker",
            part_number="UNKNOWN-001",
            category="other",
            documentation_status="missing",
            metadata=metadata(),
        )

        self.assertEqual(record.documentation_status, "missing")

    def test_knowledge_source_and_evidence_distinguish_trust_and_confidence(self):
        src = source(trust="authoritative")
        ev = evidence()

        self.assertEqual(src.trust_class, "authoritative")
        self.assertEqual(ev.extraction_confidence, 1.0)
        self.assertEqual(ev.validation_state, "verified")

    def test_llm_only_verified_evidence_cannot_self_verify(self):
        with self.assertRaises(ValidationError):
            llm_evidence(state="verified")

        with self.assertRaises(ValidationError):
            llm_evidence(state="verified", validation_method="not_validated")

    def test_llm_source_backed_verified_evidence_requires_independent_validation(self):
        ev = llm_evidence(state="verified", validation_method="manual_review")

        self.assertEqual(ev.extraction_method, "future_llm_draft")
        self.assertEqual(ev.validation_state, "verified")
        self.assertEqual(ev.source_id, "SRC_DS_001")

    def test_llm_unverified_draft_evidence_is_allowed(self):
        ev = llm_evidence(state="unverified")

        self.assertEqual(ev.validation_state, "unverified")

    def test_compliance_profile_keeps_project_filtering_outside_component(self):
        profile = ComplianceProfile(
            profile_id="CP_AUTOMOTIVE_001",
            domain="automotive",
            required_qualifications=["AEC_Q100"],
            preferred_standards=["ISO_26262"],
            metadata=metadata(),
        )

        self.assertEqual(profile.required_qualifications, ["AEC_Q100"])
        self.assertFalse(hasattr(component(), "required_qualifications"))

    def test_engineering_rule_creation_and_applicability(self):
        rule = EngineeringRule(
            rule_id="RULE_IF_001",
            category="interface",
            applicability=RuleApplicability(interface_type="i2c"),
            statement="I2C implementations require pull-up behavior on SDA and SCL.",
            severity="required",
            source_ids=["SRC_DS_001"],
            metadata=metadata(),
        )

        self.assertEqual(rule.applicability.interface_type, "i2c")
        self.assertEqual(rule.severity, "required")


class KnowledgeRepositoryTests(unittest.TestCase):
    def test_repository_rejects_duplicate_ids_and_dangling_refs(self):
        repo = repository_with_component()
        with self.assertRaises(KnowledgeRepositoryError):
            repo.add_source(source())

        with self.assertRaises(KnowledgeRepositoryError):
            repo.add_component(component(component_id="CMP_OTHER_ID"))

        dangling = component(component_id="CMP_DANGLING", part_number="DANGLING")
        data = dangling.model_dump(mode="json")
        data["attributes"][0]["evidence_ids"] = ["EVID_MISSING"]
        with self.assertRaises(KnowledgeRepositoryError):
            repo.add_component(ComponentRecord.model_validate(data))

    def test_existing_component_enrichment_preserves_identity_and_merges_new_source(self):
        repo = repository_with_component()
        repo.add_source(source("SRC_DS_REV_B"))
        repo.add_evidence(evidence("EVID_DS_REV_B", "SRC_DS_REV_B"))
        incoming = component(
            component_id="CMP_SHOULD_NOT_BE_USED",
            source_id="SRC_DS_REV_B",
            evidence_id="EVID_DS_REV_B",
        )

        result = repo.upsert_component(incoming)
        merged = repo.find_component_by_identity(incoming.identity())

        self.assertEqual(result.status, KnowledgeImportStatus.UPDATED_EXISTING)
        self.assertEqual(result.component_id, "CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001")
        self.assertIn("SRC_DS_REV_B", merged.source_ids)
        self.assertEqual(len(repo.components), 1)

    def test_exact_duplicate_import_returns_duplicate_and_does_not_mutate(self):
        repo = InMemoryKnowledgeRepository()
        repo.add_source(source())
        repo.add_evidence(evidence())
        first = repo.upsert_component(component(), result_id="KIR_FIRST")
        before = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001").model_dump(mode="json")

        second = repo.upsert_component(component(), result_id="KIR_SECOND")
        after = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001").model_dump(mode="json")

        self.assertEqual(first.status, KnowledgeImportStatus.CREATED)
        self.assertEqual(second.status, KnowledgeImportStatus.DUPLICATE)
        self.assertEqual(len(repo.components), 1)
        self.assertEqual(before, after)

    def test_conflicting_new_knowledge_is_preserved_without_overwrite(self):
        repo = repository_with_component()
        repo.add_source(source("SRC_CONFLICT"))
        repo.add_evidence(evidence("EVID_CONFLICT", "SRC_CONFLICT"))
        incoming = component(
            component_id="CMP_CONFLICT",
            source_id="SRC_CONFLICT",
            evidence_id="EVID_CONFLICT",
        )
        data = incoming.model_dump(mode="json")
        data["attributes"][1]["value"]["value"]["value"] = 2
        incoming = ComponentRecord.model_validate(data)

        result = repo.upsert_component(incoming)
        merged = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001")

        self.assertEqual(result.status, KnowledgeImportStatus.NEEDS_REVIEW)
        self.assertEqual(len(result.conflicts), 1)
        currents = [attr for attr in merged.attributes if attr.name == "maximum_output_current"]
        self.assertEqual(len(currents), 2)
        self.assertIn(KnowledgeState.CONFLICTING, {attr.status for attr in currents})
        self.assertNotEqual(result.status, KnowledgeImportStatus.DUPLICATE)

    def test_manual_entry_can_create_component_without_datasheet(self):
        repo = InMemoryKnowledgeRepository()
        entry = ManualKnowledgeEntry(
            manual_entry_id="MAN_001",
            component_identity=ComponentIdentity(manufacturer="Bench Drawer", part_number="BD-RES-10K"),
            attribute_name="resistance",
            value=QuantityExactValue(value=quantity(10000, "ohm")),
            note="Measured by technician.",
            source_description="Technician note",
            evidence_state="unverified",
            metadata=metadata(),
        )

        result = repo.apply_manual_entry(entry, category="resistor")
        record = repo.get_component(result.component_id)

        self.assertEqual(result.status, KnowledgeImportStatus.CREATED)
        self.assertEqual(record.documentation_status, "user_supplied_only")
        self.assertEqual(record.attributes[0].status, "unverified")
        self.assertEqual(repo.sources["SRC_MAN_001"].trust_class, "unverified")

    def test_manual_entry_enriches_existing_component(self):
        repo = repository_with_component()
        entry = ManualKnowledgeEntry(
            manual_entry_id="MAN_002",
            component_id="CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001",
            attribute_name="package",
            value={"kind": "text", "value": "Synthetic-QFN"},
            note="Internal AVL note.",
            source_description="Internal package note",
            evidence_state="unverified",
            source_trust="curated_internal",
            metadata=metadata(),
        )

        result = repo.apply_manual_entry(entry)
        record = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001")

        self.assertEqual(result.status, KnowledgeImportStatus.UPDATED_EXISTING)
        self.assertIn("package", {attribute.name for attribute in record.attributes})
        self.assertEqual(repo.sources["SRC_MAN_002"].trust_class, "curated_internal")

    def test_compliance_filtering_keeps_unknown_distinct_from_verified_no(self):
        repo = InMemoryKnowledgeRepository()
        repo.add_source(source())
        repo.add_evidence(evidence())
        component_a = component(
            component_id="CMP_A",
            part_number="A",
            claims=[
                claim("CLAIM_A_AEC", "AEC_Q100"),
                claim("CLAIM_A_ISO", "ISO_26262", claim_type="supports_target_integrity_level"),
            ],
        )
        component_b = component(
            component_id="CMP_B",
            part_number="B",
            claims=[
                claim("CLAIM_B_AEC", "AEC_Q100"),
                claim("CLAIM_B_ISO", "ISO_26262", state="unknown", claim_type="supports_target_integrity_level"),
            ],
        )
        component_c = component(
            component_id="CMP_C",
            part_number="C",
            claims=[claim("CLAIM_C_AEC", "AEC_Q100", state="verified_no")],
        )
        repo.add_component(component_a)
        repo.add_component(component_b)
        repo.add_component(component_c)

        required_aec = KnowledgeQuery(
            query_id="KQ_AEC",
            filters=KnowledgeFilter(required_qualifications=["AEC_Q100"]),
            metadata=metadata(),
        )
        result = repo.query(required_aec)
        self.assertEqual({item.component_id for item in result.component_records}, {"CMP_A", "CMP_B"})

        required_aec_iso = KnowledgeQuery(
            query_id="KQ_AEC_ISO",
            filters=KnowledgeFilter(required_qualifications=["AEC_Q100", "ISO_26262"]),
            metadata=metadata(),
        )
        result = repo.query(required_aec_iso)
        self.assertEqual([item.component_id for item in result.component_records], ["CMP_A"])

        preferred_iso = KnowledgeQuery(
            query_id="KQ_AEC_ISO_PREF",
            filters=KnowledgeFilter(required_qualifications=["AEC_Q100"], preferred_qualifications=["ISO_26262"]),
            metadata=metadata(),
        )
        result = repo.query(preferred_iso)
        self.assertEqual({item.component_id for item in result.component_records}, {"CMP_A", "CMP_B"})
        self.assertIn("preferred_qualification=ISO_26262", result.applied_filters)
        self.assertEqual(len(result.unresolved_knowledge), 1)

    def test_query_filters_by_category_attribute_trust_cad_and_returns_context(self):
        repo = repository_with_component()
        repo.add_source(kicad_library_source("SRC_KICAD", locator="fixture"))
        symbol_ref = {
            "library": "Regulator",
            "symbol_name": "SYN_PWR_001",
            "source_id": "SRC_KICAD",
            "verified_exists": True,
            "metadata": metadata().model_dump(mode="json"),
        }
        data = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001").model_dump(mode="json")
        data["symbol_references"].append(symbol_ref)
        repo.components[data["component_id"]] = ComponentRecord.model_validate(data)
        repo.add_rule(
            EngineeringRule(
                rule_id="RULE_PWR_001",
                category="power",
                applicability=RuleApplicability(component_category="power_converter"),
                statement="Power converters require input and output decoupling analysis.",
                severity="recommended",
                source_ids=["SRC_DS_001"],
                metadata=metadata(),
            )
        )
        query = KnowledgeQuery(
            query_id="KQ_PWR",
            filters=KnowledgeFilter(
                category="power_converter",
                attribute_constraints=[
                    AttributeConstraint(
                        name="input_voltage",
                        required_value=QuantityExactValue(value=quantity(12, "V")),
                    )
                ],
                required_qualifications=["AEC_Q100"],
                require_symbol=True,
                minimum_source_trust="authoritative",
            ),
            metadata=metadata(),
        )

        context = repo.query(query)

        self.assertEqual([item.component_id for item in context.component_records], ["CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001"])
        self.assertEqual([rule.rule_id for rule in context.engineering_rules], ["RULE_PWR_001"])
        self.assertIn("SRC_DS_001", context.source_ids)
        self.assertIn("SRC_DS_001", {source.source_id for source in context.sources})
        self.assertIn("EVID_DS_001", {item.evidence_id for item in context.evidence})
        self.assertIn("require_symbol=true", context.applied_filters)

    def test_knowledge_context_provenance_closure_excludes_unrelated_records(self):
        repo = repository_with_component()
        repo.add_source(source("SRC_UNRELATED"))
        repo.add_evidence(evidence("EVID_UNRELATED", "SRC_UNRELATED"))
        query = KnowledgeQuery(
            query_id="KQ_PROVENANCE",
            filters=KnowledgeFilter(category="power_converter"),
            metadata=metadata(),
        )

        context = repo.query(query)

        self.assertEqual([item.component_id for item in context.component_records], ["CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001"])
        self.assertEqual({item.evidence_id for item in context.evidence}, {"EVID_DS_001"})
        self.assertEqual({item.source_id for item in context.sources}, {"SRC_DS_001"})
        self.assertEqual(context.source_ids, ["SRC_DS_001"])

    def test_knowledge_context_missing_provenance_fails_deterministically(self):
        repo = repository_with_component()
        del repo.evidence["EVID_DS_001"]
        query = KnowledgeQuery(
            query_id="KQ_MISSING_PROVENANCE",
            filters=KnowledgeFilter(category="power_converter"),
            metadata=metadata(),
        )

        with self.assertRaises(KnowledgeRepositoryError):
            repo.query(query)

    def test_empty_query_returns_valid_empty_context_without_recursion(self):
        repo = InMemoryKnowledgeRepository()
        query = KnowledgeQuery(
            query_id="KQ_EMPTY",
            filters=KnowledgeFilter(category="regulator"),
            metadata=metadata(),
        )

        context = repo.query(query)
        restored = type(context).model_validate_json(context.model_dump_json())

        self.assertEqual(context.component_records, [])
        self.assertEqual(context.engineering_rules, [])
        self.assertEqual(context.sources, [])
        self.assertEqual(context.evidence, [])
        self.assertEqual(context.source_ids, [])
        self.assertEqual(restored.model_dump(mode="json"), context.model_dump(mode="json"))

    def test_no_match_filter_returns_valid_empty_context(self):
        repo = repository_with_component()
        query = KnowledgeQuery(
            query_id="KQ_NO_MATCH",
            filters=KnowledgeFilter(category="regulator"),
            metadata=metadata(),
        )

        context = repo.query(query)

        self.assertEqual(context.component_records, [])
        self.assertEqual(context.sources, [])
        self.assertEqual(context.evidence, [])
        self.assertEqual(context.source_ids, [])

    def test_knowledge_context_model_rejects_incomplete_provenance(self):
        from schematic_ai.domain.knowledge import KnowledgeContext

        query = KnowledgeQuery(query_id="KQ_BAD_CONTEXT", metadata=metadata())
        with self.assertRaises(ValidationError):
            KnowledgeContext(
                context_id="KCTX_BAD",
                query=query,
                component_records=[component()],
                sources=[source()],
                evidence=[],
                metadata=metadata(),
            )

    def test_empty_context_source_id_consistency_validates(self):
        from schematic_ai.domain.knowledge import KnowledgeContext

        context = KnowledgeContext(
            context_id="KCTX_EMPTY_MANUAL",
            query=KnowledgeQuery(query_id="KQ_EMPTY_MANUAL", metadata=metadata()),
            sources=[],
            evidence=[],
            source_ids=[],
            metadata=metadata(),
        )

        self.assertEqual(context.source_ids, [])

    def test_unknown_to_verified_claim_enrichment_preserves_evidence_and_enables_retrieval(self):
        repo = InMemoryKnowledgeRepository()
        repo.add_source(source())
        repo.add_evidence(evidence())
        unknown_component = component(
            claims=[claim("CLAIM_AEC_UNKNOWN", "AEC_Q100", state="unknown")],
        )
        repo.add_component(unknown_component)
        before = repo.query(
            KnowledgeQuery(
                query_id="KQ_BEFORE_AEC",
                filters=KnowledgeFilter(required_qualifications=["AEC_Q100"]),
                metadata=metadata(),
            )
        )
        self.assertEqual(before.component_records, [])

        repo.add_source(source("SRC_AEC_VERIFIED"))
        repo.add_evidence(evidence("EVID_AEC_VERIFIED", "SRC_AEC_VERIFIED"))
        incoming = component(
            component_id="CMP_INCOMING_AEC",
            source_id="SRC_AEC_VERIFIED",
            evidence_id="EVID_AEC_VERIFIED",
            claims=[
                claim(
                    "CLAIM_AEC_VERIFIED",
                    "AEC_Q100",
                    state="verified",
                    source_id="SRC_AEC_VERIFIED",
                    evidence_id="EVID_AEC_VERIFIED",
                )
            ],
        )

        result = repo.upsert_component(incoming)
        after = repo.query(
            KnowledgeQuery(
                query_id="KQ_AFTER_AEC",
                filters=KnowledgeFilter(required_qualifications=["AEC_Q100"]),
                metadata=metadata(),
            )
        )
        merged = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001")

        self.assertEqual(result.status, KnowledgeImportStatus.UPDATED_EXISTING)
        self.assertEqual(result.component_id, "CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001")
        self.assertEqual([item.component_id for item in after.component_records], ["CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001"])
        states = {claim.evidence_state for claim in merged.qualification_claims}
        self.assertIn(KnowledgeState.UNKNOWN, states)
        self.assertIn(KnowledgeState.VERIFIED, states)
        evidence_ids = {evidence_id for claim in merged.qualification_claims for evidence_id in claim.evidence_ids}
        self.assertIn("EVID_AEC_VERIFIED", evidence_ids)

    def test_multiple_supporting_claim_evidence_is_preserved(self):
        repo = repository_with_component()
        repo.add_source(source("SRC_QUAL_PAGE"))
        repo.add_evidence(evidence("EVID_QUAL_PAGE", "SRC_QUAL_PAGE"))
        incoming = component(
            component_id="CMP_SUPPORTING",
            source_id="SRC_QUAL_PAGE",
            evidence_id="EVID_QUAL_PAGE",
            claims=[
                claim(
                    "CLAIM_AEC_PAGE",
                    "AEC_Q100",
                    source_id="SRC_QUAL_PAGE",
                    evidence_id="EVID_QUAL_PAGE",
                )
            ],
        )

        result = repo.upsert_component(incoming)
        merged = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001")

        self.assertEqual(result.status, KnowledgeImportStatus.UPDATED_EXISTING)
        self.assertIn("EVID_QUAL_PAGE", {evidence_id for claim in merged.qualification_claims for evidence_id in claim.evidence_ids})
        self.assertGreaterEqual(len(merged.qualification_claims), 2)

    def test_exact_claim_duplicate_is_noop(self):
        repo = repository_with_component()
        before = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001").model_dump(mode="json")

        result = repo.upsert_component(component())
        after = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001").model_dump(mode="json")

        self.assertEqual(result.status, KnowledgeImportStatus.DUPLICATE)
        self.assertEqual(before, after)

    def test_conflicting_claim_evidence_is_preserved_and_needs_review(self):
        repo = repository_with_component()
        repo.add_source(source("SRC_AEC_NO"))
        repo.add_evidence(evidence("EVID_AEC_NO", "SRC_AEC_NO"))
        incoming = component(
            component_id="CMP_AEC_NO",
            source_id="SRC_AEC_NO",
            evidence_id="EVID_AEC_NO",
            claims=[
                claim(
                    "CLAIM_AEC_NO",
                    "AEC_Q100",
                    state="verified_no",
                    source_id="SRC_AEC_NO",
                    evidence_id="EVID_AEC_NO",
                )
            ],
        )

        result = repo.upsert_component(incoming)
        merged = repo.get_component("CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001")

        self.assertEqual(result.status, KnowledgeImportStatus.NEEDS_REVIEW)
        self.assertEqual(len(result.conflicts), 1)
        states = {claim.evidence_state for claim in merged.qualification_claims}
        self.assertIn(KnowledgeState.VERIFIED, states)
        self.assertIn(KnowledgeState.VERIFIED_NO, states)

    def test_rule_with_dangling_source_is_rejected_by_repository(self):
        repo = InMemoryKnowledgeRepository()
        rule = EngineeringRule(
            rule_id="RULE_IF_001",
            category="interface",
            applicability=RuleApplicability(interface_type="i2c"),
            statement="I2C implementations require pull-up behavior on SDA and SCL.",
            severity="required",
            source_ids=["SRC_MISSING"],
            metadata=metadata(),
        )

        with self.assertRaises(KnowledgeRepositoryError):
            repo.add_rule(rule)


class KiCadIndexingTests(unittest.TestCase):
    def test_symbol_indexing_uses_real_fixture_entries_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Regulator.kicad_sym").write_text(
                '(kicad_symbol_lib (version 20231120) (symbol "SYN_PWR_001" (pin_names)))',
                encoding="utf-8",
            )

            entries = index_kicad_symbols(root)
            ref = symbol_reference_if_exists(
                library="Regulator",
                symbol_name="SYN_PWR_001",
                source_id="SRC_KICAD",
                symbol_dir=root,
            )
            missing = symbol_reference_if_exists(
                library="Regulator",
                symbol_name="MISSING",
                source_id="SRC_KICAD",
                symbol_dir=root,
            )

        self.assertEqual(entries[0].symbol_name, "SYN_PWR_001")
        self.assertTrue(ref.verified_exists)
        self.assertIsNone(missing)

    def test_footprint_indexing_keeps_package_mapping_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pretty = root / "Package_QFN.pretty"
            pretty.mkdir()
            (pretty / "QFN_16_SYN.kicad_mod").write_text("(footprint \"QFN_16_SYN\")", encoding="utf-8")

            entries = index_kicad_footprints(root)
            ref = footprint_reference_if_exists(
                library="Package_QFN",
                footprint_name="QFN_16_SYN",
                package_mapping="VQFN-16",
                source_id="SRC_KICAD",
                footprint_dir=root,
            )
            missing = footprint_reference_if_exists(
                library="Package_QFN",
                footprint_name="MISSING",
                source_id="SRC_KICAD",
                footprint_dir=root,
            )

        self.assertEqual(entries[0].footprint_name, "QFN_16_SYN")
        self.assertEqual(ref.package_mapping, "VQFN-16")
        self.assertTrue(ref.verified_exists)
        self.assertIsNone(missing)


class KnowledgeSchemaTests(unittest.TestCase):
    def test_major_contract_schemas_generate(self):
        self.assertEqual(ComponentRecord.model_json_schema()["title"], "ComponentRecord")
        self.assertEqual(EngineeringRule.model_json_schema()["title"], "EngineeringRule")
        from schematic_ai.domain.knowledge import KnowledgeContext

        self.assertEqual(KnowledgeContext.model_json_schema()["title"], "KnowledgeContext")

    def test_query_serializes_losslessly(self):
        query = KnowledgeQuery(
            query_id="KQ_JSON",
            filters=KnowledgeFilter(category="power_converter", required_qualifications=["AEC_Q100"]),
            metadata=metadata(),
        )

        restored = KnowledgeQuery.model_validate_json(query.model_dump_json())
        self.assertEqual(restored.model_dump(mode="json"), query.model_dump(mode="json"))


if __name__ == "__main__":
    unittest.main()
