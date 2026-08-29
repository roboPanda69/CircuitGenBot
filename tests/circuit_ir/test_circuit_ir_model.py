import copy
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from schematic_ai.application.knowledge import kicad_library_source
from schematic_ai.domain.circuit_ir import (
    CircuitIR,
    CircuitIRContextValidationError,
    CircuitIRMetadata,
    ComponentInstance,
    ComponentResolutionStatus,
    Net,
    PinInstance,
    next_circuit_revision,
    validate_circuit_ir_against_design_plan,
    validate_circuit_ir_against_knowledge,
)
from schematic_ai.domain.design_plan import DesignPlan
from schematic_ai.domain.knowledge import (
    ComponentRecord,
    Evidence,
    KnowledgeContext,
    KnowledgeMetadata,
    KnowledgeQuery,
    KnowledgeSource,
)


ROOT = Path(__file__).resolve().parents[2]
CIRCUIT_IR_PATH = ROOT / "examples" / "circuit_ir_v0_1.json"
DESIGN_PLAN_PATH = ROOT / "examples" / "design_plan_v0_1.json"
COMPONENT_RECORD_PATH = ROOT / "examples" / "component_record_v0_1.json"


def metadata_dict(created_by="unit_test"):
    return {
        "created_at": "2026-08-29T00:00:00+05:30",
        "updated_at": "2026-08-29T00:00:00+05:30",
        "created_by": created_by,
    }


def circuit_ir_data():
    return json.loads(CIRCUIT_IR_PATH.read_text(encoding="utf-8"))


def design_plan_data():
    return json.loads(DESIGN_PLAN_PATH.read_text(encoding="utf-8"))


def circuit_ir():
    return CircuitIR.model_validate(circuit_ir_data())


def design_plan():
    return DesignPlan.model_validate(design_plan_data())


def component_record():
    return ComponentRecord.model_validate_json(COMPONENT_RECORD_PATH.read_text(encoding="utf-8"))


def minimal_circuit_data():
    return {
        "schema_version": "0.1",
        "circuit_id": "CIR_MIN_001",
        "project_id": "PRJ_0001",
        "revision": 1,
        "source_design_plan": {"design_plan_id": "DPLAN_0001", "revision": 1},
        "implementation_status": "unresolved",
        "components": [],
        "nets": [],
        "interface_bindings": [],
        "implementation_mappings": [],
        "assumptions": [],
        "open_decisions": [],
        "groups": [],
        "knowledge_references": [],
        "metadata": metadata_dict(),
    }


def knowledge_context():
    return KnowledgeContext(
        context_id="KCTX_CIRCUIT_IR_001",
        query=KnowledgeQuery(query_id="KQ_CIRCUIT_IR_001", metadata=KnowledgeMetadata(created_by="unit_test")),
        component_records=[component_record()],
        sources=[
            KnowledgeSource(
                source_id="SRC_DS_001",
                source_type="manufacturer_datasheet",
                title="Synthetic Power Converter Datasheet",
                publisher_or_manufacturer="Synthetic Semiconductor",
                document_identifier="SYN-PWR-001-DS",
                revision="A",
                locator="tests/fixtures/synthetic_power_converter.pdf",
                trust_class="authoritative",
                metadata=KnowledgeMetadata(created_by="unit_test"),
            ),
            kicad_library_source("SRC_KICAD_001", locator="tests/fixtures/kicad"),
        ],
        evidence=[
            Evidence(
                evidence_id="EVID_DS_001",
                source_id="SRC_DS_001",
                locator="page 12 electrical characteristics",
                extraction_method="manual",
                extraction_confidence=1.0,
                validation_state="verified",
                validation_method="manual_review",
                metadata=KnowledgeMetadata(created_by="unit_test"),
            )
        ],
        metadata=KnowledgeMetadata(created_by="unit_test"),
    )


def first_component(data, instance_id):
    return next(component for component in data["components"] if component["instance_id"] == instance_id)


def first_net(data, net_id):
    return next(net for net in data["nets"] if net["net_id"] == net_id)


def fully_resolved_circuit_data():
    data = circuit_ir_data()
    data["implementation_status"] = "resolved"
    data["open_decisions"] = []
    for component in data["components"]:
        component["resolution_status"] = "resolved"
        component["component_record_id"] = "CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001"
        component["implementation_status"] = "resolved"
        for pin in component["pins"]:
            pin["resolution_status"] = "resolved"
            if pin["connection_state"] == "unresolved":
                pin["connection_state"] = "connected"
    data["nets"].append(
        {
            "net_id": "NET_SW",
            "name": "SW",
            "net_class": "switching_node",
            "connections": [{"component_instance_id": "U_REG_001", "pin_id": "PIN_U_REG_SW"}],
            "role": "signal",
            "power_domain_id": None,
            "properties": [],
            "metadata": metadata_dict(),
        }
    )
    for mapping in data["implementation_mappings"]:
        mapping["status"] = "resolved"
    return data


class CircuitIRModelTests(unittest.TestCase):
    def assert_invalid(self, mutator):
        data = circuit_ir_data()
        mutator(data)
        with self.assertRaises(ValidationError):
            CircuitIR.model_validate(data)

    def test_minimal_valid_circuit_ir(self):
        model = CircuitIR.model_validate(minimal_circuit_data())

        self.assertEqual(model.schema_version, "0.1")
        self.assertEqual(model.components, [])
        self.assertEqual(model.nets, [])

    def test_example_serializes_round_trips_and_schema_generates(self):
        model = circuit_ir()
        restored = CircuitIR.model_validate_json(model.model_dump_json())

        self.assertEqual(restored.model_dump(mode="json"), model.model_dump(mode="json"))
        self.assertEqual(CircuitIR.model_json_schema()["title"], "CircuitIR")

    def test_resolved_and_unresolved_components_are_explicit_states(self):
        model = circuit_ir()
        resolved = next(component for component in model.components if component.instance_id == "U_REG_001")
        unresolved = next(component for component in model.components if component.instance_id == "D_PROT_001")

        self.assertEqual(resolved.resolution_status, ComponentResolutionStatus.RESOLVED)
        self.assertEqual(resolved.component_record_id, "CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001")
        self.assertEqual(unresolved.resolution_status, ComponentResolutionStatus.UNRESOLVED)
        self.assertIsNone(unresolved.component_record_id)

    def test_resolved_component_requires_component_record_id(self):
        self.assert_invalid(lambda data: first_component(data, "U_REG_001").update({"component_record_id": None}))

    def test_component_implementation_resolved_requires_resolved_identity(self):
        self.assert_invalid(lambda data: first_component(data, "D_PROT_001").update({"implementation_status": "resolved"}))

    def test_component_implementation_resolved_requires_resolved_pins(self):
        self.assert_invalid(
            lambda data: first_component(data, "U_REG_001").update({"implementation_status": "resolved"})
        )

    def test_partially_resolved_component_can_have_structured_value_without_record(self):
        model = circuit_ir()
        c_in = next(component for component in model.components if component.instance_id == "C_IN_001")

        self.assertEqual(c_in.resolution_status, "partially_resolved")
        self.assertIsNone(c_in.component_record_id)
        self.assertEqual(c_in.value.quantity.value, 22)
        self.assertEqual(c_in.value.quantity.unit, "uF")

    def test_pin_ownership_is_validated_inside_component(self):
        data = first_component(circuit_ir_data(), "C_IN_001")
        data["pins"][0]["component_instance_id"] = "OTHER_COMPONENT"

        with self.assertRaises(ValidationError):
            ComponentInstance.model_validate(data)

    def test_duplicate_pin_on_multiple_nets_is_rejected(self):
        self.assert_invalid(
            lambda data: first_net(data, "NET_5V")["connections"].append(
                {"component_instance_id": "C_IN_001", "pin_id": "PIN_C_IN_POS"}
            )
        )

    def test_dangling_net_references_are_rejected(self):
        self.assert_invalid(lambda data: first_net(data, "NET_5V")["connections"][0].update({"component_instance_id": "U_MISSING"}))
        self.assert_invalid(lambda data: first_net(data, "NET_5V")["connections"][0].update({"pin_id": "PIN_MISSING"}))

    def test_net_connection_must_reference_pin_owned_by_component(self):
        self.assert_invalid(lambda data: first_net(data, "NET_5V")["connections"][0].update({"component_instance_id": "C_OUT_001"}))

    def test_no_connect_pins_are_distinct_from_unresolved_pins(self):
        model = circuit_ir()
        u_reg = next(component for component in model.components if component.instance_id == "U_REG_001")
        en_pin = next(pin for pin in u_reg.pins if pin.pin_id == "PIN_U_REG_EN")
        sw_pin = next(pin for pin in u_reg.pins if pin.pin_id == "PIN_U_REG_SW")

        self.assertEqual(en_pin.connection_state, "no_connect")
        self.assertEqual(sw_pin.connection_state, "unresolved")
        self.assert_invalid(
            lambda data: first_net(data, "NET_5V")["connections"].append(
                {"component_instance_id": "U_REG_001", "pin_id": "PIN_U_REG_EN"}
            )
        )

    def test_unresolved_pin_on_net_is_rejected(self):
        self.assert_invalid(
            lambda data: first_net(data, "NET_5V")["connections"].append(
                {"component_instance_id": "U_REG_001", "pin_id": "PIN_U_REG_SW"}
            )
        )

    def test_connected_pin_on_exactly_one_net_is_valid(self):
        model = circuit_ir()
        connected_pin_ids = [
            connection.pin_id
            for net in model.nets
            for connection in net.connections
            if connection.component_instance_id == "U_REG_001"
        ]

        self.assertIn("PIN_U_REG_VOUT", connected_pin_ids)

    def test_unresolved_pin_without_net_is_valid(self):
        model = circuit_ir()
        sw_pin = next(
            pin
            for component in model.components
            if component.instance_id == "U_REG_001"
            for pin in component.pins
            if pin.pin_id == "PIN_U_REG_SW"
        )

        self.assertEqual(sw_pin.connection_state, "unresolved")

    def test_connected_pin_must_appear_on_net(self):
        def mutate(data):
            first_net(data, "NET_5V")["connections"] = [
                connection
                for connection in first_net(data, "NET_5V")["connections"]
                if connection["pin_id"] != "PIN_U_REG_VOUT"
            ]

        self.assert_invalid(mutate)

    def test_implementation_mapping_circuit_object_refs_are_validated(self):
        self.assert_invalid(lambda data: data["implementation_mappings"][0]["circuit_object_ids"].append("NET_MISSING"))

    def test_empty_implementation_mapping_is_rejected(self):
        self.assert_invalid(
            lambda data: data["implementation_mappings"].append(
                {
                    "mapping_id": "CIMAP_EMPTY_001",
                    "design_plan_object_ids": [],
                    "circuit_object_ids": [],
                    "mapping_type": "implements",
                    "status": "resolved",
                    "rationale": "invalid empty mapping",
                }
            )
        )

    def test_one_sided_implementation_mapping_is_rejected(self):
        self.assert_invalid(lambda data: data["implementation_mappings"][0].update({"circuit_object_ids": []}))
        self.assert_invalid(lambda data: data["implementation_mappings"][0].update({"design_plan_object_ids": []}))

    def test_net_roles_and_separate_ground_nets_are_preserved(self):
        model = circuit_ir()
        roles = {net.net_id: net.role for net in model.nets}
        net_names = {net.net_id: net.name for net in model.nets}

        self.assertEqual(roles["NET_5V"], "power")
        self.assertEqual(roles["NET_GND"], "ground")
        self.assertEqual(roles["NET_AGND"], "ground")
        self.assertEqual(net_names["NET_GND"], "GND")
        self.assertEqual(net_names["NET_AGND"], "AGND")
        self.assertNotEqual(model.nets[3].net_id, model.nets[4].net_id)

    def test_structured_net_properties_are_quantity_values(self):
        model = circuit_ir()
        net_5v = next(net for net in model.nets if net.net_id == "NET_5V")

        self.assertEqual(net_5v.properties[0].value.quantity.value, 5)
        self.assertEqual(net_5v.properties[0].value.quantity.unit, "V")

    def test_standalone_pin_and_net_models_generate_schemas(self):
        self.assertEqual(PinInstance.model_json_schema()["title"], "PinInstance")
        self.assertEqual(Net.model_json_schema()["title"], "Net")

    def test_revision_helper_is_immutable(self):
        original = circuit_ir()
        updated = next_circuit_revision(original)

        self.assertEqual(original.revision, 1)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(original.circuit_id, updated.circuit_id)
        self.assertGreaterEqual(updated.metadata.updated_at, original.metadata.updated_at)

    def test_metadata_rejects_naive_datetime(self):
        with self.assertRaises(ValidationError):
            CircuitIRMetadata(
                created_at="2026-08-29T00:00:00",
                updated_at="2026-08-29T00:00:00",
                created_by="unit_test",
            )

    def test_false_resolved_circuit_with_unresolved_component_is_rejected(self):
        self.assert_invalid(lambda data: data.update({"implementation_status": "resolved"}))

    def test_false_resolved_circuit_with_partial_component_is_rejected(self):
        def mutate(data):
            resolved = fully_resolved_circuit_data()
            data.clear()
            data.update(resolved)
            first_component(data, "C_IN_001")["resolution_status"] = "partially_resolved"
            first_component(data, "C_IN_001")["implementation_status"] = "partial"

        self.assert_invalid(mutate)

    def test_false_resolved_circuit_with_unresolved_pin_is_rejected(self):
        def mutate(data):
            resolved = fully_resolved_circuit_data()
            data.clear()
            data.update(resolved)
            first_component(data, "U_REG_001")["pins"][1]["connection_state"] = "unresolved"
            data["nets"] = [net for net in data["nets"] if net["net_id"] != "NET_SW"]

        self.assert_invalid(mutate)

    def test_false_resolved_circuit_with_blocking_decision_is_rejected(self):
        def mutate(data):
            resolved = fully_resolved_circuit_data()
            original = circuit_ir_data()
            data.clear()
            data.update(resolved)
            data["open_decisions"] = [copy.deepcopy(original["open_decisions"][0])]

        self.assert_invalid(mutate)

    def test_false_resolved_circuit_with_partial_mapping_is_rejected(self):
        def mutate(data):
            resolved = fully_resolved_circuit_data()
            data.clear()
            data.update(resolved)
            data["implementation_mappings"][0]["status"] = "partial"

        self.assert_invalid(mutate)

    def test_partial_circuit_may_contain_progressive_unresolved_state(self):
        model = circuit_ir()

        self.assertEqual(model.implementation_status, "partial")
        self.assertTrue(any(component.resolution_status == "unresolved" for component in model.components))
        self.assertTrue(any(decision.blocking for decision in model.open_decisions))

    def test_fully_resolved_structural_circuit_is_valid_without_verification(self):
        model = CircuitIR.model_validate(fully_resolved_circuit_data())

        self.assertEqual(model.implementation_status, "resolved")
        self.assertEqual({mapping.status for mapping in model.implementation_mappings}, {"resolved"})
        self.assertEqual(model.open_decisions, [])


class CircuitIRContextValidationTests(unittest.TestCase):
    def test_example_validates_against_design_plan_and_knowledge_context(self):
        model = circuit_ir()

        validate_circuit_ir_against_design_plan(model, design_plan())
        validate_circuit_ir_against_knowledge(model, knowledge_context())

    def test_source_design_plan_identity_mismatch_is_rejected(self):
        data = circuit_ir_data()
        data["source_design_plan"]["design_plan_id"] = "DPLAN_OTHER"
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_design_plan(model, design_plan())

    def test_source_design_plan_revision_mismatch_is_rejected(self):
        data = circuit_ir_data()
        data["source_design_plan"]["revision"] = 99
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_design_plan(model, design_plan())

    def test_component_source_block_ids_must_exist_in_design_plan(self):
        data = circuit_ir_data()
        first_component(data, "C_IN_001")["source_block_ids"].append("BLOCK_MISSING")
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_design_plan(model, design_plan())

    def test_implementation_mapping_design_plan_ids_must_exist(self):
        data = circuit_ir_data()
        data["implementation_mappings"][0]["design_plan_object_ids"].append("BLOCK_MISSING")
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_design_plan(model, design_plan())

    def test_interface_binding_must_reference_known_design_plan_interface(self):
        data = circuit_ir_data()
        data["interface_bindings"][0]["design_plan_interface_id"] = "IF_MISSING"
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_design_plan(model, design_plan())

    def test_power_domain_ids_must_exist_in_design_plan(self):
        data = circuit_ir_data()
        first_net(data, "NET_5V")["power_domain_id"] = "PWRDOM_MISSING"
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_design_plan(model, design_plan())

    def test_one_block_can_map_to_many_components(self):
        model = circuit_ir()
        power_block_components = [
            component.instance_id
            for component in model.components
            if "BLOCK_PWR_001" in component.source_block_ids
        ]

        self.assertEqual(power_block_components, ["U_REG_001", "C_IN_001", "C_OUT_001"])
        validate_circuit_ir_against_design_plan(model, design_plan())

    def test_one_component_can_trace_to_multiple_design_plan_blocks(self):
        data = circuit_ir_data()
        first_component(data, "U_REG_001")["source_block_ids"].append("BLOCK_PROT_001")
        data["implementation_mappings"][2]["design_plan_object_ids"].append("BLOCK_PROT_001")
        model = CircuitIR.model_validate(data)

        validate_circuit_ir_against_design_plan(model, design_plan())

    def test_group_source_blocks_are_contextually_validated(self):
        data = circuit_ir_data()
        data["groups"][0]["source_block_ids"].append("BLOCK_MISSING")
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_design_plan(model, design_plan())

    def test_resolved_component_must_exist_in_knowledge_context(self):
        context = knowledge_context()
        context_data = context.model_dump(mode="json")
        context_data["component_records"] = []
        context_data["source_ids"] = [source["source_id"] for source in context_data["sources"]]
        empty_context = KnowledgeContext.model_validate(context_data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_knowledge(circuit_ir(), empty_context)

    def test_unresolved_component_with_null_record_ref_is_contextually_valid(self):
        model = circuit_ir()

        validate_circuit_ir_against_knowledge(model, knowledge_context())

    def test_unresolved_component_with_valid_record_ref_is_contextually_valid(self):
        data = circuit_ir_data()
        first_component(data, "D_PROT_001")["component_record_id"] = "CMP_SYNTHETIC_SEMICONDUCTOR_SYN_PWR_001"
        model = CircuitIR.model_validate(data)

        validate_circuit_ir_against_knowledge(model, knowledge_context())

    def test_unresolved_component_with_invalid_record_ref_fails_knowledge_validation(self):
        data = circuit_ir_data()
        first_component(data, "D_PROT_001")["component_record_id"] = "CMP_FAKE"
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_knowledge(model, knowledge_context())

    def test_partially_resolved_component_with_invalid_record_ref_fails_knowledge_validation(self):
        data = circuit_ir_data()
        first_component(data, "C_IN_001")["component_record_id"] = "CMP_FAKE"
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_knowledge(model, knowledge_context())

    def test_resolved_component_with_unknown_record_ref_fails_knowledge_validation(self):
        data = circuit_ir_data()
        first_component(data, "U_REG_001")["component_record_id"] = "CMP_FAKE"
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_knowledge(model, knowledge_context())

    def test_knowledge_reference_source_and_evidence_must_exist(self):
        data = circuit_ir_data()
        first_component(data, "U_REG_001")["knowledge_references"][0]["source_ids"].append("SRC_MISSING")
        model = CircuitIR.model_validate(data)

        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_knowledge(model, knowledge_context())

        data = circuit_ir_data()
        data["knowledge_references"][0]["evidence_ids"].append("EVID_MISSING")
        model = CircuitIR.model_validate(data)
        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_knowledge(model, knowledge_context())

    def test_symbol_and_footprint_reference_sources_are_contextually_validated(self):
        record_data = component_record().model_dump(mode="json")
        data = circuit_ir_data()
        resolved = first_component(data, "U_REG_001")
        resolved["symbol_reference"] = copy.deepcopy(record_data["symbol_references"][0])
        resolved["footprint_reference"] = copy.deepcopy(record_data["footprint_references"][0])
        model = CircuitIR.model_validate(data)
        validate_circuit_ir_against_knowledge(model, knowledge_context())

        data = circuit_ir_data()
        resolved = first_component(data, "U_REG_001")
        resolved["symbol_reference"] = copy.deepcopy(record_data["symbol_references"][0])
        resolved["symbol_reference"]["source_id"] = "SRC_MISSING"
        model = CircuitIR.model_validate(data)
        with self.assertRaises(CircuitIRContextValidationError):
            validate_circuit_ir_against_knowledge(model, knowledge_context())


if __name__ == "__main__":
    unittest.main()
