from __future__ import annotations

import json
from pathlib import Path

from schematic_ai.application.circuit_planner import CircuitPlanner, CircuitPlanningContext
from schematic_ai.application.knowledge import InMemoryKnowledgeRepository, kicad_library_source
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
from schematic_ai.domain.requirements.models import RequirementModel


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_PATH = ROOT / "examples" / "requirement_model_v0_1.json"
DESIGN_PLAN_PATH = ROOT / "examples" / "design_plan_v0_1.json"
COMPONENT_PATH = ROOT / "examples" / "component_record_v0_1.json"


class FakeLLMClient:
    def generate_structured(self, *, prompt: str, json_schema: dict | None = None) -> str:
        return json.dumps(circuit_draft())


def main() -> None:
    requirement_model = RequirementModel.model_validate_json(REQUIREMENT_PATH.read_text(encoding="utf-8"))
    design_plan = DesignPlan.model_validate_json(DESIGN_PLAN_PATH.read_text(encoding="utf-8"))
    knowledge_context = example_knowledge_context()
    result = CircuitPlanner(FakeLLMClient(), max_repair_attempts=0).plan_circuit(
        CircuitPlanningContext(
            requirement_model=requirement_model,
            design_plan=design_plan,
            knowledge_context=knowledge_context,
        )
    )
    print(result.model_dump_json(indent=2))


def example_knowledge_context():
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
            metadata=KnowledgeMetadata(created_by="circuit_planner_example"),
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
            metadata=KnowledgeMetadata(created_by="circuit_planner_example"),
        )
    )
    repo.add_component(component)
    return repo.query(
        KnowledgeQuery(
            query_id="KQ_CIRCUIT_PLANNER_EXAMPLE_001",
            filters=KnowledgeFilter(
                category="power_converter",
                attribute_constraints=[
                    AttributeConstraint(
                        name="input_voltage",
                        required_value=QuantityExactValue(value=quantity(12, "V")),
                    )
                ],
            ),
            metadata=KnowledgeMetadata(created_by="circuit_planner_example"),
        )
    )


def circuit_draft() -> dict:
    return {
        "component_instances": [
            {
                "draft_id": "regulator",
                "role": "main_power_converter",
                "component_class": "converter",
                "resolution_intent": "partially_resolved",
                "proposed_component_record_id": "CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001",
                "reference_designator_hint": "U_DO_NOT_USE",
                "value": None,
                "parameters": [],
                "source_design_plan_refs": ["BLOCK_PWR_001"],
                "source_requirement_refs": ["REQ_PWR_001", "REQ_PWR_002", "REQ_PWR_003"],
                "pin_drafts": [
                    {
                        "draft_pin_id": "vin",
                        "component_draft_id": "regulator",
                        "function": "input power",
                        "pin_name": "VIN",
                        "electrical_type": "power_input",
                        "resolution_status": "unresolved",
                        "connection_intent": "connected",
                    },
                    {
                        "draft_pin_id": "vout",
                        "component_draft_id": "regulator",
                        "function": "regulated output",
                        "pin_name": "VOUT",
                        "electrical_type": "power_output",
                        "resolution_status": "unresolved",
                        "connection_intent": "connected",
                    },
                    {
                        "draft_pin_id": "gnd",
                        "component_draft_id": "regulator",
                        "function": "ground",
                        "pin_name": "GND",
                        "electrical_type": "power_input",
                        "resolution_status": "unresolved",
                        "connection_intent": "connected",
                    },
                ],
            },
            unresolved_two_pin("input_capacitor", "input_decoupling", "capacitor", "vin", "gnd"),
            unresolved_two_pin("output_capacitor", "output_decoupling", "capacitor", "vout", "gnd"),
            unresolved_two_pin("power_inductor", "output_inductor", "inductor", "vout", "open"),
        ],
        "nets": [
            {
                "draft_net_id": "vin_net",
                "name_hint": "VIN",
                "role": "power",
                "power_domain_ref": "PWRDOM_VIN_PROTECTED",
                "connections": [
                    {"component_draft_id": "regulator", "draft_pin_id": "vin"},
                    {"component_draft_id": "input_capacitor", "draft_pin_id": "input_capacitor_a"},
                ],
            },
            {
                "draft_net_id": "vout_net",
                "name_hint": "VOUT",
                "role": "power",
                "power_domain_ref": "PWRDOM_5V",
                "connections": [
                    {"component_draft_id": "regulator", "draft_pin_id": "vout"},
                    {"component_draft_id": "output_capacitor", "draft_pin_id": "output_capacitor_a"},
                    {"component_draft_id": "power_inductor", "draft_pin_id": "power_inductor_a"},
                ],
            },
            {
                "draft_net_id": "gnd_net",
                "name_hint": "GND",
                "role": "ground",
                "connections": [
                    {"component_draft_id": "regulator", "draft_pin_id": "gnd"},
                    {"component_draft_id": "input_capacitor", "draft_pin_id": "input_capacitor_b"},
                    {"component_draft_id": "output_capacitor", "draft_pin_id": "output_capacitor_b"},
                ],
            },
        ],
        "implementation_mappings": [
            {
                "draft_mapping_id": "map_power",
                "design_plan_refs": ["BLOCK_PWR_001", "PWRDOM_5V"],
                "circuit_draft_refs": ["regulator", "input_capacitor", "output_capacitor", "power_inductor", "vin_net", "vout_net", "gnd_net"],
                "mapping_type": "implements",
                "status": "partial",
                "rationale": "Draft maps the power conversion architecture into an initial electrical skeleton.",
            }
        ],
        "assumptions": [],
        "open_decisions": [
            {
                "topic": "supporting_component_values",
                "description": "Input capacitor, output capacitor, and inductor values remain unresolved pending evidence or deterministic calculation.",
                "target_draft_refs": ["input_capacitor", "output_capacitor", "power_inductor"],
                "blocking": False,
                "options": [],
                "driven_by_design_plan_refs": ["BLOCK_PWR_001"],
                "status": "open",
            }
        ],
        "metadata": {},
    }


def unresolved_two_pin(draft_id: str, role: str, component_class: str, pin_a: str, pin_b: str) -> dict:
    return {
        "draft_id": draft_id,
        "role": role,
        "component_class": component_class,
        "resolution_intent": "unresolved",
        "proposed_component_record_id": None,
        "reference_designator_hint": None,
        "value": None,
        "parameters": [],
        "source_design_plan_refs": ["BLOCK_PWR_001"],
        "source_requirement_refs": [],
        "pin_drafts": [
            {
                "draft_pin_id": f"{draft_id}_a",
                "component_draft_id": draft_id,
                "function": pin_a,
                "pin_name": None,
                "electrical_type": "passive",
                "resolution_status": "unresolved",
                "connection_intent": "connected",
            },
            {
                "draft_pin_id": f"{draft_id}_b",
                "component_draft_id": draft_id,
                "function": pin_b,
                "pin_name": None,
                "electrical_type": "passive",
                "resolution_status": "unresolved",
                "connection_intent": "unresolved" if pin_b == "open" else "connected",
            },
        ],
    }


if __name__ == "__main__":
    main()
