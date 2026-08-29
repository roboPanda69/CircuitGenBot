from __future__ import annotations

from pathlib import Path

from schematic_ai.application.knowledge import InMemoryKnowledgeRepository, kicad_library_source
from schematic_ai.domain.knowledge import (
    AttributeConstraint,
    ComponentRecord,
    ComplianceProfile,
    EngineeringRule,
    Evidence,
    KnowledgeFilter,
    KnowledgeMetadata,
    KnowledgeQuery,
    KnowledgeSource,
    QuantityExactValue,
    quantity,
)


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_PATH = ROOT / "examples" / "component_record_v0_1.json"
RULE_PATH = ROOT / "examples" / "engineering_rule_v0_1.json"
PROFILE_PATH = ROOT / "examples" / "compliance_profile_v0_1.json"


def main() -> None:
    component = ComponentRecord.model_validate_json(COMPONENT_PATH.read_text(encoding="utf-8"))
    rule = EngineeringRule.model_validate_json(RULE_PATH.read_text(encoding="utf-8"))
    profile = ComplianceProfile.model_validate_json(PROFILE_PATH.read_text(encoding="utf-8"))

    repo = InMemoryKnowledgeRepository()
    repo.add_source(
        KnowledgeSource(
            source_id="SRC_DS_001",
            source_type="manufacturer_datasheet",
            title="Synthetic Power Converter Datasheet",
            publisher_or_manufacturer="Synthetic Semiconductor",
            document_identifier="SYN-PWR-001-DS",
            revision="A",
            locator="examples/synthetic/SYN-PWR-001-datasheet.pdf",
            trust_class="authoritative",
            metadata=KnowledgeMetadata(created_by="knowledge_fixture"),
        )
    )
    repo.add_source(kicad_library_source("SRC_KICAD_001", locator="examples/kicad-fixture"))
    repo.add_source(
        KnowledgeSource(
            source_id="SRC_RULE_001",
            source_type="internal_document",
            title="Synthetic interface rule fixture",
            locator="docs/architecture/engineering-knowledge-v0.1.md",
            trust_class="curated_internal",
            metadata=KnowledgeMetadata(created_by="knowledge_fixture"),
        )
    )
    repo.add_evidence(
        Evidence(
            evidence_id="EVID_DS_001",
            source_id="SRC_DS_001",
            locator="page 12 electrical characteristics",
            extraction_method="manual",
            extraction_confidence=1.0,
            validation_state="verified",
            validation_method="manual_review",
            metadata=KnowledgeMetadata(created_by="knowledge_fixture"),
        )
    )
    repo.add_component(component)
    repo.add_rule(rule)
    context = repo.query(
        KnowledgeQuery(
            query_id="KQ_EXAMPLE_001",
            filters=KnowledgeFilter(
                category="power_converter",
                attribute_constraints=[
                    AttributeConstraint(
                        name="input_voltage",
                        required_value=QuantityExactValue(value=quantity(12, "V")),
                    )
                ],
                required_qualifications=profile.required_qualifications,
                preferred_compliance=profile.preferred_standards,
                require_symbol=True,
            ),
            metadata=KnowledgeMetadata(created_by="knowledge_fixture"),
        )
    )
    print(
        f"Validated {component.component_id}, {rule.rule_id}, {profile.profile_id}; "
        f"context {context.context_id} returned {len(context.component_records)} component(s)"
    )


if __name__ == "__main__":
    main()
