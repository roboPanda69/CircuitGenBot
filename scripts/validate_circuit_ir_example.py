from __future__ import annotations

from pathlib import Path

from schematic_ai.application.knowledge import InMemoryKnowledgeRepository, kicad_library_source
from schematic_ai.domain.circuit_ir import (
    CircuitIR,
    validate_circuit_ir_against_design_plan,
    validate_circuit_ir_against_knowledge,
)
from schematic_ai.domain.design_plan import DesignPlan
from schematic_ai.domain.knowledge import (
    AttributeConstraint,
    ComponentRecord,
    Evidence,
    KnowledgeFilter,
    KnowledgeMetadata,
    KnowledgeQuery,
    KnowledgeSource,
    QuantityExactValue,
    quantity,
)


ROOT = Path(__file__).resolve().parents[1]
CIRCUIT_IR_PATH = ROOT / "examples" / "circuit_ir_v0_1.json"
DESIGN_PLAN_PATH = ROOT / "examples" / "design_plan_v0_1.json"
COMPONENT_PATH = ROOT / "examples" / "component_record_v0_1.json"


def main() -> None:
    circuit_ir = CircuitIR.model_validate_json(CIRCUIT_IR_PATH.read_text(encoding="utf-8"))
    design_plan = DesignPlan.model_validate_json(DESIGN_PLAN_PATH.read_text(encoding="utf-8"))
    component = ComponentRecord.model_validate_json(COMPONENT_PATH.read_text(encoding="utf-8"))

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
            metadata=KnowledgeMetadata(created_by="circuit_ir_fixture"),
        )
    )
    repo.add_source(kicad_library_source("SRC_KICAD_001", locator="examples/kicad-fixture"))
    repo.add_evidence(
        Evidence(
            evidence_id="EVID_DS_001",
            source_id="SRC_DS_001",
            locator="page 12 electrical characteristics",
            extraction_method="manual",
            extraction_confidence=1.0,
            validation_state="verified",
            validation_method="manual_review",
            metadata=KnowledgeMetadata(created_by="circuit_ir_fixture"),
        )
    )
    repo.add_component(component)
    knowledge_context = repo.query(
        KnowledgeQuery(
            query_id="KQ_CIRCUIT_IR_EXAMPLE_001",
            filters=KnowledgeFilter(
                category="power_converter",
                attribute_constraints=[
                    AttributeConstraint(
                        name="input_voltage",
                        required_value=QuantityExactValue(value=quantity(12, "V")),
                    )
                ],
            ),
            metadata=KnowledgeMetadata(created_by="circuit_ir_fixture"),
        )
    )

    validate_circuit_ir_against_design_plan(circuit_ir, design_plan)
    validate_circuit_ir_against_knowledge(circuit_ir, knowledge_context)
    print(
        f"Validated {circuit_ir.circuit_id} revision {circuit_ir.revision}: "
        f"{len(circuit_ir.components)} component(s), {len(circuit_ir.nets)} net(s)"
    )


if __name__ == "__main__":
    main()
