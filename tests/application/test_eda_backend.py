import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from schematic_ai.application.eda import (
    FootprintResolver,
    GenerationContext,
    GenerationDiagnosticCategory,
    GenerationStatus,
    KiCadArtifactChecker,
    KiCadBackend,
    PinMappingResolver,
    PythonCircuitRepresentationBackend,
    SchematicLayoutStrategy,
    SymbolResolver,
)
from schematic_ai.application.eda.checker import parse_sexpr
from schematic_ai.domain.circuit_ir import CircuitIR


def metadata_dict(created_by="eda_test"):
    return {
        "created_at": "2026-08-30T00:00:00+05:30",
        "updated_at": "2026-08-30T00:00:00+05:30",
        "created_by": created_by,
    }


def symbol_ref(library="Device", symbol_name="R", verified=True):
    return {
        "library": library,
        "symbol_name": symbol_name,
        "source_id": "SRC_KICAD_001",
        "verified_exists": verified,
        "metadata": metadata_dict(),
    }


def footprint_ref(library="Resistor_SMD", footprint_name="R_0603_1608Metric", verified=True):
    return {
        "library": library,
        "footprint_name": footprint_name,
        "package_mapping": "synthetic test mapping",
        "source_id": "SRC_KICAD_001",
        "verified_exists": verified,
        "metadata": metadata_dict(),
    }


def pin(component_id, pin_id, number, name, *, state="connected", resolution="resolved", electrical_type="passive"):
    return {
        "pin_id": pin_id,
        "component_instance_id": component_id,
        "pin_number": number,
        "pin_name": name,
        "electrical_type": electrical_type,
        "function": name.lower() if name else None,
        "resolution_status": resolution,
        "connection_state": state,
        "metadata": metadata_dict(),
    }


def component(
    instance_id,
    refdes,
    component_class,
    pins,
    *,
    role=None,
    resolution="resolved",
    implementation="resolved",
    value=None,
    symbol=None,
    footprint=None,
):
    return {
        "instance_id": instance_id,
        "reference_designator": refdes,
        "component_class": component_class,
        "role": role,
        "resolution_status": resolution,
        "component_record_id": f"CMP_{instance_id}" if resolution == "resolved" else None,
        "value": value,
        "parameters": [],
        "pins": pins,
        "source_block_ids": [],
        "source_requirement_ids": [],
        "knowledge_references": [],
        "symbol_reference": symbol,
        "footprint_reference": footprint,
        "implementation_status": implementation,
        "metadata": metadata_dict(),
    }


def quantity_value(value, unit):
    return {"kind": "quantity", "quantity": {"value": value, "unit": unit}}


def circuit_data(*, components, nets, status="resolved", circuit_id="CIR_EDA_001", revision=3):
    return {
        "schema_version": "0.1",
        "circuit_id": circuit_id,
        "project_id": "PRJ_EDA_001",
        "revision": revision,
        "source_design_plan": {"design_plan_id": "DPLAN_EDA_001", "revision": 1},
        "implementation_status": status,
        "components": components,
        "nets": nets,
        "interface_bindings": [],
        "implementation_mappings": [],
        "assumptions": [],
        "open_decisions": [],
        "groups": [],
        "knowledge_references": [],
        "metadata": metadata_dict(),
    }


def net(net_id, name, connections, role="signal"):
    return {
        "net_id": net_id,
        "name": name,
        "net_class": None,
        "connections": connections,
        "role": role,
        "power_domain_id": None,
        "properties": [],
        "metadata": metadata_dict(),
    }


def resolved_circuit():
    j1 = component(
        "J_IN_001",
        "J1",
        "connector",
        [
            pin("J_IN_001", "PIN_J1_1", "1", "VIN", electrical_type="power_output"),
            pin("J_IN_001", "PIN_J1_2", "2", "GND", electrical_type="power_output"),
        ],
        role="12v_input_connector",
        symbol=symbol_ref("Connector_Generic", "Conn_01x02"),
        footprint=footprint_ref("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical"),
    )
    r1 = component(
        "R_LOAD_001",
        "R1",
        "resistor",
        [
            pin("R_LOAD_001", "PIN_R1_1", "1", "1"),
            pin("R_LOAD_001", "PIN_R1_2", "2", "2"),
        ],
        role="load_resistor",
        value=quantity_value(10, "kOhm"),
        symbol=symbol_ref("Device", "R"),
        footprint=footprint_ref(),
    )
    c1 = component(
        "C_OUT_001",
        "C1",
        "capacitor",
        [
            pin("C_OUT_001", "PIN_C1_1", "1", "1"),
            pin("C_OUT_001", "PIN_C1_2", "2", "2"),
        ],
        role="output_capacitor",
        value=quantity_value(22, "uF"),
        symbol=symbol_ref("Device", "C"),
        footprint=footprint_ref("Capacitor_SMD", "C_0603_1608Metric"),
    )
    nets = [
        net("NET_VIN", "VIN", [{"component_instance_id": "J_IN_001", "pin_id": "PIN_J1_1"}, {"component_instance_id": "R_LOAD_001", "pin_id": "PIN_R1_1"}], "power"),
        net("NET_GND", "GND", [{"component_instance_id": "J_IN_001", "pin_id": "PIN_J1_2"}, {"component_instance_id": "C_OUT_001", "pin_id": "PIN_C1_2"}], "ground"),
        net("NET_VOUT", "VOUT", [{"component_instance_id": "R_LOAD_001", "pin_id": "PIN_R1_2"}, {"component_instance_id": "C_OUT_001", "pin_id": "PIN_C1_1"}], "power"),
    ]
    return CircuitIR.model_validate(circuit_data(components=[j1, r1, c1], nets=nets))


def unresolved_regulator_circuit():
    u1 = component(
        "U_REG_001",
        "U1",
        "regulator",
        [
            pin("U_REG_001", "PIN_U1_IN", None, "IN", resolution="unresolved", electrical_type="power_input"),
            pin("U_REG_001", "PIN_U1_OUT", None, "OUT", resolution="unresolved", electrical_type="power_output"),
            pin("U_REG_001", "PIN_U1_GND", None, "GND", resolution="unresolved", electrical_type="power_input"),
        ],
        role="switching_regulator",
        resolution="unresolved",
        implementation="partial",
    )
    nets = [
        net("NET_VIN", "VIN", [{"component_instance_id": "U_REG_001", "pin_id": "PIN_U1_IN"}], "power"),
        net("NET_5V", "5V", [{"component_instance_id": "U_REG_001", "pin_id": "PIN_U1_OUT"}], "power"),
        net("NET_GND", "GND", [{"component_instance_id": "U_REG_001", "pin_id": "PIN_U1_GND"}], "ground"),
    ]
    return CircuitIR.model_validate(circuit_data(components=[u1], nets=nets, status="partial"))


FIXTURE_SYMBOL_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "kicad9_symbols"


def endpoint_for(result, pin_id):
    return next(
        endpoint
        for mapping in result.manifest.object_mappings
        if mapping.source_object_type == "component_instance"
        for endpoint in mapping.metadata["pin_endpoints"]
        if endpoint["circuit_pin_id"] == pin_id
    )


def connection_point(result, pin_id):
    endpoint = endpoint_for(result, pin_id)
    point = endpoint["connection_point"]
    return point["x"], point["y"]


def label_at(label, point, uuid_text):
    x, y = point
    return (
        f'  (global_label "{label}"\n'
        "    (shape input)\n"
        f"    (at {x} {y} 0)\n"
        f'    (uuid "{uuid_text}")\n'
        '    (effects (font (size 1.27 1.27)) (justify left))\n'
        "  )\n"
    )


def local_label_at(label, point, uuid_text):
    x, y = point
    return (
        f'  (label "{label}"\n'
        f"    (at {x} {y} 0)\n"
        f'    (uuid "{uuid_text}")\n'
        '    (effects (font (size 1.27 1.27)) (justify left bottom))\n'
        "  )\n"
    )


def annotation_text_at(text, point, uuid_text):
    x, y = point
    return (
        f'  (text "{text}"\n'
        f"    (at {x} {y} 0)\n"
        f'    (uuid "{uuid_text}")\n'
        '    (effects (font (size 1.0 1.0)) (justify left))\n'
        "  )\n"
    )


def no_connect_at(point, uuid_text):
    x, y = point
    return f'  (no_connect (at {x} {y})\n    (uuid "{uuid_text}")\n  )\n'


def wire_between(start, end, uuid_text):
    sx, sy = start
    ex, ey = end
    return (
        "  (wire\n"
        f"    (pts (xy {sx} {sy}) (xy {ex} {ey}))\n"
        '    (stroke (width 0) (type default))\n'
        f'    (uuid "{uuid_text}")\n'
        "  )\n"
    )


def junction_at(point, uuid_text):
    x, y = point
    return f'  (junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid "{uuid_text}"))\n'


def insert_before_symbol_instances(schematic, block):
    return schematic.replace("\n  (symbol_instances", f"\n{block}  (symbol_instances", 1)


def remove_top_level_block(schematic, head):
    marker = f"\n  ({head}"
    start = schematic.index(marker) + 1
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(schematic)):
        char = schematic[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                end = index + 1
                if end < len(schematic) and schematic[end] == "\n":
                    end += 1
                return schematic[:start] + schematic[end:]
    raise AssertionError(f"could not remove top-level block {head}")


def extract_balanced_block(text, start):
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                end = index + 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return text[start:end]
    raise AssertionError("could not extract balanced block")


def path_block_for(schematic, symbol_uuid):
    start = schematic.index(f'    (path "/{symbol_uuid}"')
    return extract_balanced_block(schematic, start)


def remove_path_for(schematic, symbol_uuid):
    block = path_block_for(schematic, symbol_uuid)
    return schematic.replace(block, "", 1)


def component_symbol_block(schematic, component_id):
    property_marker = f'(property "CircuitIR_ID" "{component_id}"'
    property_index = schematic.index(property_marker)
    start = schematic.rfind("\n  (symbol\n", 0, property_index) + 1
    return extract_balanced_block(schematic, start)


def remove_all_placed_pin_records(schematic):
    return re.sub(r'\n    \(pin "[^"]+" \(uuid "[^"]+"\)\)', "", schematic)


def remove_first_placed_pin_record(schematic, pin_number):
    return re.sub(r'\n    \(pin "' + re.escape(pin_number) + r'" \(uuid "[^"]+"\)\)', "", schematic, count=1)


def first_pin_uuid(schematic):
    return re.search(r'\n    \(pin "[^"]+" \(uuid "([^"]+)"\)\)', schematic).group(1)


def symbol_uuid_for(result, component_id):
    return next(
        mapping.backend_object_id
        for mapping in result.manifest.object_mappings
        if mapping.source_object_type == "component_instance" and mapping.source_object_id == component_id
    )


def unexpected_symbol_block(schematic, result, *, seed, circuit_id):
    block = component_symbol_block(schematic, "R_LOAD_001")
    uuid_index = 0

    def replace_uuid(_match):
        nonlocal uuid_index
        uuid_index += 1
        return f'(uuid "{seed:08x}-0000-0000-0000-{uuid_index:012d}")'

    block = re.sub(r'\(uuid "[^"]+"\)', replace_uuid, block)
    return (
        block.replace('(property "Reference" "R1"', f'(property "Reference" "X{seed}"', 1)
        .replace('(property "Value" "10 kOhm"', '(property "Value" "extra"', 1)
        .replace('(property "CircuitIR_ID" "R_LOAD_001"', f'(property "CircuitIR_ID" "{circuit_id}"', 1)
    )


def circuit_with_agnd_connector():
    data = resolved_circuit().model_dump(mode="json")
    j2 = component(
        "J_AGND_001",
        "J2",
        "connector",
        [
            pin("J_AGND_001", "PIN_J2_1", "1", "AGND", electrical_type="power_output"),
            pin("J_AGND_001", "PIN_J2_2", "2", "NC", state="no_connect", electrical_type="no_connect"),
        ],
        role="analog_ground_test_connector",
        symbol=symbol_ref("Connector_Generic", "Conn_01x02"),
        footprint=footprint_ref("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical"),
    )
    data["components"].append(j2)
    data["nets"].append(net("NET_AGND", "AGND", [{"component_instance_id": "J_AGND_001", "pin_id": "PIN_J2_1"}], "ground"))
    return CircuitIR.model_validate(data)


def circuit_with_expected_no_connect():
    data = resolved_circuit().model_dump(mode="json")
    data["components"][0]["pins"][1]["connection_state"] = "no_connect"
    data["components"][0]["pins"][1]["electrical_type"] = "no_connect"
    data["nets"][1]["connections"] = [
        connection
        for connection in data["nets"][1]["connections"]
        if connection["pin_id"] != "PIN_J1_2"
    ]
    return CircuitIR.model_validate(data)


def circuit_with_supported_real_unresolved_pin():
    resistor = component(
        "R_LOAD_001",
        "R1",
        "resistor",
        [
            pin("R_LOAD_001", "PIN_R1_1", "1", "1"),
            pin("R_LOAD_001", "PIN_R1_PENDING", "2", "2", state="unresolved"),
        ],
        role="partially_connected_resistor",
        implementation="partial",
        value=quantity_value(10, "kOhm"),
        symbol=symbol_ref("Device", "R"),
        footprint=footprint_ref(),
    )
    return CircuitIR.model_validate(
        circuit_data(
            components=[resistor],
            nets=[
                net(
                    "NET_IN",
                    "IN",
                    [{"component_instance_id": "R_LOAD_001", "pin_id": "PIN_R1_1"}],
                )
            ],
            status="partial",
        )
    )


def circuit_with_placeholder_unresolved_pin():
    unknown = component(
        "U_UNKNOWN_001",
        "U1",
        "regulator",
        [
            pin("U_UNKNOWN_001", "PIN_UNKNOWN_IN", None, "IN", resolution="unresolved"),
            pin(
                "U_UNKNOWN_001",
                "PIN_UNKNOWN_PENDING",
                None,
                "PENDING",
                state="unresolved",
                resolution="unresolved",
            ),
        ],
        resolution="unresolved",
        implementation="partial",
    )
    return CircuitIR.model_validate(
        circuit_data(
            components=[unknown],
            nets=[net("NET_IN", "IN", [{"component_instance_id": "U_UNKNOWN_001", "pin_id": "PIN_UNKNOWN_IN"}])],
            status="partial",
        )
    )


class EDABackendTests(unittest.TestCase):
    def generate_kicad(self, circuit):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = KiCadBackend().generate(
                circuit,
                GenerationContext(output_dir=Path(temp_dir), kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )
            files = {file.path: (Path(temp_dir) / file.path).read_text(encoding="utf-8") for file in result.generated_files if file.path.endswith((".kicad_sch", ".json"))}
            return result, files

    def test_backend_capabilities_report_one_way_kicad_generation(self):
        capabilities = KiCadBackend().capabilities()

        self.assertTrue(capabilities.supports_schematic)
        self.assertTrue(capabilities.supports_footprints)
        self.assertTrue(capabilities.supports_placeholders)
        self.assertTrue(capabilities.supports_partial_circuit)
        self.assertTrue(capabilities.deterministic_generation)
        self.assertFalse(capabilities.supports_round_trip)
        self.assertEqual(capabilities.target_version, "9")

    def test_resolved_kicad_generation_preserves_refdes_values_and_connectivity(self):
        result, files = self.generate_kicad(resolved_circuit())
        schematic = files["circuit.kicad_sch"]

        self.assertEqual(result.status, GenerationStatus.SUCCESS)
        self.assertIn('(property "Reference" "R1"', schematic)
        self.assertIn('(property "Value" "10 kOhm"', schematic)
        self.assertIn('(property "Value" "22 uF"', schematic)
        self.assertIn('(lib_id "Device:R")', schematic)
        self.assertIn("(symbol_instances", schematic)
        self.assertIn("(sheet_instances", schematic)
        self.assertIn('(reference "R1")', schematic)
        self.assertEqual(result.manifest.metadata["connectivity"]["NET_VIN"][0]["pin_id"], "PIN_J1_1")
        self.assertEqual(len(result.manifest.placeholders), 0)
        self.assertTrue(result.manifest.metadata["artifact_check"]["valid"])
        self.assertEqual(
            result.manifest.metadata["artifact_check"]["generated_connectivity"]["NET_VIN"],
            ["J_IN_001:PIN_J1_1", "R_LOAD_001:PIN_R1_1"],
        )

    def test_unresolved_component_generates_editable_placeholder_with_traceability(self):
        result, files = self.generate_kicad(unresolved_regulator_circuit())
        schematic = files["circuit.kicad_sch"]

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertIn("SchematicAI:PLACEHOLDER_U_REG_001", schematic)
        self.assertIn('(property "SchematicAI_Status" "PLACEHOLDER"', schematic)
        self.assertIn('(property "CircuitIR_ID" "U_REG_001"', schematic)
        self.assertEqual(result.manifest.placeholders[0].source_instance_id, "U_REG_001")
        self.assertEqual(result.manifest.placeholders[0].metadata["pin_labels"], {"PIN_U1_IN": "IN", "PIN_U1_OUT": "OUT", "PIN_U1_GND": "GND"})
        self.assertEqual(
            result.manifest.metadata["artifact_check"]["generated_connectivity"]["NET_VIN"],
            ["U_REG_001:PIN_U1_IN"],
        )

    def test_resolved_component_without_symbol_is_not_silently_guessed(self):
        circuit = resolved_circuit()
        data = circuit.model_dump(mode="json")
        data["implementation_status"] = "partial"
        data["components"][1]["symbol_reference"] = None
        data["components"][1]["implementation_status"] = "partial"
        result, _ = self.generate_kicad(CircuitIR.model_validate(data))

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        categories = {diagnostic.category for diagnostic in result.diagnostics}
        self.assertIn(GenerationDiagnosticCategory.MISSING_SYMBOL, categories)
        self.assertEqual(result.manifest.placeholders[0].source_instance_id, "R_LOAD_001")

    def test_missing_footprint_does_not_block_schematic_generation(self):
        data = resolved_circuit().model_dump(mode="json")
        data["implementation_status"] = "partial"
        data["components"][1]["footprint_reference"] = None
        data["components"][1]["implementation_status"] = "partial"
        result, _ = self.generate_kicad(CircuitIR.model_validate(data))

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertIn(GenerationDiagnosticCategory.MISSING_FOOTPRINT, {diagnostic.category for diagnostic in result.diagnostics})
        self.assertTrue(any(file.path == "circuit.kicad_sch" for file in result.generated_files))

    def test_untrusted_pin_mapping_falls_back_to_placeholder(self):
        data = resolved_circuit().model_dump(mode="json")
        data["implementation_status"] = "partial"
        data["components"][1]["implementation_status"] = "partial"
        data["components"][1]["pins"][0]["resolution_status"] = "partially_resolved"
        data["components"][1]["pins"][0]["pin_number"] = None
        result, files = self.generate_kicad(CircuitIR.model_validate(data))

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertIn(GenerationDiagnosticCategory.UNRESOLVED_PIN_MAPPING, {diagnostic.category for diagnostic in result.diagnostics})
        self.assertIn("SchematicAI:PLACEHOLDER_R_LOAD_001", files["circuit.kicad_sch"])

    def test_ground_nets_are_not_merged(self):
        data = resolved_circuit().model_dump(mode="json")
        data["nets"].append(net("NET_AGND", "AGND", [], "ground"))
        result, files = self.generate_kicad(CircuitIR.model_validate(data))

        self.assertEqual(result.status, GenerationStatus.SUCCESS)
        self.assertIn("NET_GND", files["circuit.kicad_sch"])
        self.assertIn("NET_AGND", files["circuit.kicad_sch"])
        self.assertIn("NET_GND", result.manifest.metadata["connectivity"])
        self.assertIn("NET_AGND", result.manifest.metadata["connectivity"])

    def test_no_connect_and_unresolved_pin_states_remain_distinct(self):
        data = resolved_circuit().model_dump(mode="json")
        data["implementation_status"] = "partial"
        extra_nc = pin("R_LOAD_001", "PIN_R1_NC", "3", "NC", state="no_connect", electrical_type="no_connect")
        extra_unresolved = pin("R_LOAD_001", "PIN_R1_PENDING", "4", "PENDING", state="unresolved", resolution="resolved")
        data["components"][1]["pins"].extend([extra_nc, extra_unresolved])
        data["components"][1]["implementation_status"] = "partial"
        result, files = self.generate_kicad(CircuitIR.model_validate(data))

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertIn("(no_connect", files["circuit.kicad_sch"])
        self.assertIn({"component_instance_id": "R_LOAD_001", "pin_id": "PIN_R1_NC"}, result.manifest.metadata["no_connects"])
        self.assertIn({"component_instance_id": "R_LOAD_001", "pin_id": "PIN_R1_PENDING"}, result.manifest.metadata["unresolved_pins"])
        self.assertEqual(result.manifest.metadata["artifact_check"]["generated_no_connects"], ["R_LOAD_001:PIN_R1_NC"])

    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            backend = KiCadBackend()
            result_a = backend.generate(resolved_circuit(), GenerationContext(output_dir=Path(left)))
            result_b = backend.generate(resolved_circuit(), GenerationContext(output_dir=Path(right)))

            self.assertEqual((Path(left) / "circuit.kicad_sch").read_text(encoding="utf-8"), (Path(right) / "circuit.kicad_sch").read_text(encoding="utf-8"))
            self.assertEqual(result_a.manifest.model_dump(mode="json"), result_b.manifest.model_dump(mode="json"))

    def test_manifest_records_circuit_revision_and_object_mappings(self):
        result, files = self.generate_kicad(resolved_circuit())
        manifest = json.loads(files["artifact_manifest.json"])

        self.assertEqual(manifest["source_circuit_id"], "CIR_EDA_001")
        self.assertEqual(manifest["source_circuit_revision"], 3)
        mapped_sources = {mapping["source_object_id"] for mapping in manifest["object_mappings"]}
        self.assertIn("R_LOAD_001", mapped_sources)
        self.assertIn("NET_VIN", mapped_sources)
        resistor_mapping = next(mapping for mapping in manifest["object_mappings"] if mapping["source_object_id"] == "R_LOAD_001")
        self.assertEqual(resistor_mapping["metadata"]["lib_id"], "Device:R")

    def test_artifact_checker_detects_missing_endpoint_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            schematic_path.write_text(
                schematic_path.read_text(encoding="utf-8").replace('(global_label "NET_VOUT"', '(global_label "NET_VOUT_REMOVED"', 1),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("NET_VOUT" in mismatch for mismatch in check.net_mismatches))

    def test_artifact_checker_detects_extra_net_merge(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            schematic_path.write_text(
                schematic_path.read_text(encoding="utf-8").replace('(global_label "NET_VOUT"', '(global_label "NET_VIN"'),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("NET_VIN" in mismatch for mismatch in check.net_mismatches))
        self.assertTrue(any("NET_VOUT" in mismatch for mismatch in check.net_mismatches))

    def test_artifact_checker_detects_conflicting_labels_at_same_node(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            conflict = label_at("NET_VOUT", connection_point(result, "PIN_J1_1"), "00000000-0000-0000-0000-000000000011")
            schematic_path.write_text(
                insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), conflict),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("conflicting canonical labels" in mismatch for mismatch in check.net_mismatches))

    def test_artifact_checker_detects_wire_merge_between_distinct_nets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            merge_wire = wire_between(
                connection_point(result, "PIN_J1_1"),
                connection_point(result, "PIN_R1_2"),
                "00000000-0000-0000-0000-000000000012",
            )
            schematic_path.write_text(
                insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), merge_wire),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("conflicting canonical labels" in mismatch for mismatch in check.net_mismatches))

    def test_artifact_checker_keeps_ground_aliases_separate_when_wired(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = circuit_with_agnd_connector()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            merge_wire = wire_between(
                connection_point(result, "PIN_J1_2"),
                connection_point(result, "PIN_J2_1"),
                "00000000-0000-0000-0000-000000000013",
            )
            schematic_path.write_text(
                insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), merge_wire),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("NET_AGND" in mismatch and "NET_GND" in mismatch for mismatch in check.net_mismatches))

    def test_artifact_checker_splits_wires_at_junctions_and_label_nodes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            vin_a = connection_point(result, "PIN_J1_1")
            vin_b = connection_point(result, "PIN_R1_1")
            junction = ((vin_a[0] + vin_b[0]) / 2, vin_a[1])
            branch = "".join(
                [
                    wire_between(vin_a, vin_b, "00000000-0000-0000-0000-000000000014"),
                    junction_at(junction, "00000000-0000-0000-0000-000000000015"),
                    label_at("NET_VIN", junction, "00000000-0000-0000-0000-000000000016"),
                ]
            )
            schematic_path.write_text(
                insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), branch),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertTrue(check.valid)
        self.assertEqual(check.generated_connectivity["NET_VIN"], ["J_IN_001:PIN_J1_1", "R_LOAD_001:PIN_R1_1"])

    def test_artifact_checker_does_not_merge_crossing_wires_without_junction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            cross = "".join(
                [
                    wire_between((40.0, 80.0), (100.0, 80.0), "00000000-0000-0000-0000-000000000017"),
                    wire_between((70.0, 60.0), (70.0, 100.0), "00000000-0000-0000-0000-000000000018"),
                ]
            )
            schematic_path.write_text(
                insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), cross),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertTrue(check.valid)

    def test_artifact_checker_detects_no_connect_label_and_wire_contradictions(self):
        data = resolved_circuit().model_dump(mode="json")
        data["implementation_status"] = "partial"
        data["components"][1]["pins"].append(pin("R_LOAD_001", "PIN_R1_NC", "3", "NC", state="no_connect", electrical_type="no_connect"))
        data["components"][1]["implementation_status"] = "partial"
        circuit = CircuitIR.model_validate(data)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            nc_point = connection_point(result, "PIN_R1_NC")
            contradiction = "".join(
                [
                    label_at("NET_VIN", nc_point, "00000000-0000-0000-0000-000000000019"),
                    wire_between(nc_point, connection_point(result, "PIN_J1_1"), "00000000-0000-0000-0000-000000000020"),
                ]
            )
            schematic_path.write_text(
                insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), contradiction),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("label-connected" in mismatch for mismatch in check.no_connect_mismatches))
        self.assertTrue(any("is wired" in mismatch for mismatch in check.no_connect_mismatches))

    def test_artifact_checker_detects_kicad_structural_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            mutations = {
                "unsupported version": base.replace("(version 20250114)", "(version 20240101)", 1),
                "malformed uuid": base.replace('(uuid "', '(uuid "not-a-uuid-', 1),
                "missing sheet instances": remove_top_level_block(base, "sheet_instances"),
                "malformed symbol instance": base.replace('      (reference "R1")\n', "", 1),
            }

            for name, schematic in mutations.items():
                with self.subTest(name=name):
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)
                    self.assertFalse(check.valid)
                    self.assertTrue(check.parse_errors)

    def test_artifact_checker_rejects_direct_symbol_instance_mutations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            r_uuid = symbol_uuid_for(result, "R_LOAD_001")
            mutations = {
                "remove all instance pins": remove_all_placed_pin_records(base),
                "remove placed symbol unit": base.replace("    (unit 1)\n", "", 1),
                "malformed path uuid": base.replace(f'    (path "/{r_uuid}"', '    (path "/not-a-uuid"', 1),
                "missing path value": base.replace('      (value "10 kOhm")\n', "", 1),
            }

            for name, schematic in mutations.items():
                with self.subTest(name=name):
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)
                    self.assertFalse(check.valid)
                    self.assertTrue(check.parse_errors)

    def test_artifact_checker_rejects_symbol_instances_path_integrity_mutations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            r_uuid = symbol_uuid_for(result, "R_LOAD_001")
            c_uuid = symbol_uuid_for(result, "C_OUT_001")
            r_path = path_block_for(base, r_uuid)
            orphan_path = r_path.replace(f'/{r_uuid}', "/00000000-0000-0000-0000-000000000101", 1)
            mutations = {
                "path reference mismatch": base.replace('      (reference "R1")\n', '      (reference "R2")\n', 1),
                "path unit mismatch": base.replace('      (unit 1)\n', '      (unit 2)\n', 1),
                "path value mismatch": base.replace('      (value "10 kOhm")\n', '      (value "22 kOhm")\n', 1),
                "path uuid points to other symbol": base.replace(f'    (path "/{r_uuid}"', f'    (path "/{c_uuid}"', 1),
                "missing path": remove_path_for(base, r_uuid),
                "duplicate path": base.replace("  )\n  (sheet_instances", f"{r_path}  )\n  (sheet_instances", 1),
                "orphan path": base.replace("  )\n  (sheet_instances", f"{orphan_path}  )\n  (sheet_instances", 1),
            }

            for name, schematic in mutations.items():
                with self.subTest(name=name):
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)
                    self.assertFalse(check.valid)
                    self.assertTrue(check.parse_errors)

    def test_symbol_instances_paths_use_native_kicad_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            for component_id in ("J_IN_001", "R_LOAD_001", "C_OUT_001"):
                with self.subTest(component_id=component_id):
                    path_block = path_block_for(base, symbol_uuid_for(result, component_id))
                    self.assertNotIn("(lib_id", path_block)

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertTrue(check.valid)

    def test_artifact_checker_rejects_private_path_field_and_placed_library_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            r_uuid = symbol_uuid_for(result, "R_LOAD_001")
            r_path = path_block_for(base, r_uuid)
            r_symbol = component_symbol_block(base, "R_LOAD_001")
            mutations = {
                "private path lib_id": base.replace(
                    r_path,
                    r_path.replace('      (value "10 kOhm")\n', '      (value "10 kOhm")\n      (lib_id "Device:R")\n', 1),
                    1,
                ),
                "placed symbol lib_id mismatch": base.replace(
                    r_symbol,
                    r_symbol.replace('(lib_id "Device:R")', '(lib_id "Device:C")', 1),
                    1,
                ),
            }

            for name, schematic in mutations.items():
                with self.subTest(name=name):
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)
                    self.assertFalse(check.valid)
                    self.assertTrue(check.parse_errors)

    def test_artifact_checker_rejects_placed_pin_instance_integrity_mutations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            first_pin_line = re.search(r'\n    \(pin "1" \(uuid "[^"]+"\)\)', base).group(0)
            duplicate_number_line = '\n    (pin "1" (uuid "00000000-0000-0000-0000-000000000201"))'
            extra_pin_line = '\n    (pin "999" (uuid "00000000-0000-0000-0000-000000000202"))'
            duplicate_uuid = first_pin_uuid(base)
            mutations = {
                "missing placed pin": remove_first_placed_pin_record(base, "2"),
                "extra placed pin": base.replace(first_pin_line, first_pin_line + extra_pin_line, 1),
                "duplicate pin number": base.replace(first_pin_line, first_pin_line + duplicate_number_line, 1),
                "duplicate pin uuid": re.sub(r'\n    \(pin "2" \(uuid "[^"]+"\)\)', f'\n    (pin "2" (uuid "{duplicate_uuid}"))', base, count=1),
                "malformed pin uuid": re.sub(r'\n    \(pin "1" \(uuid "[^"]+"\)\)', '\n    (pin "1" (uuid "not-a-pin-uuid"))', base, count=1),
            }

            for name, schematic in mutations.items():
                with self.subTest(name=name):
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)
                    self.assertFalse(check.valid)
                    self.assertTrue(check.parse_errors)

    def test_artifact_checker_rejects_unexpected_and_duplicate_placed_symbols(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            r_block = component_symbol_block(base, "R_LOAD_001")
            unexpected_block = (
                r_block.replace(symbol_uuid_for(result, "R_LOAD_001"), "00000000-0000-0000-0000-000000000301", 1)
                .replace('(property "Reference" "R1"', '(property "Reference" "RX"', 1)
                .replace('(property "Value" "10 kOhm"', '(property "Value" "extra"', 1)
                .replace('(property "CircuitIR_ID" "R_LOAD_001"', '(property "CircuitIR_ID" "EXTRA_001"', 1)
            )
            duplicate_block = r_block.replace(symbol_uuid_for(result, "R_LOAD_001"), "00000000-0000-0000-0000-000000000302", 1)
            mutations = {
                "unexpected extra symbol": base.replace("\n  (symbol_instances", f"\n{unexpected_block}  (symbol_instances", 1),
                "duplicate representation": base.replace("\n  (symbol_instances", f"\n{duplicate_block}  (symbol_instances", 1),
            }

            for name, schematic in mutations.items():
                with self.subTest(name=name):
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)
                    self.assertFalse(check.valid)
                    self.assertTrue(check.parse_errors)

    def test_artifact_checker_accounts_for_every_malformed_raw_placed_symbol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            extra = unexpected_symbol_block(base, result, seed=0x601, circuit_id="EXTRA_MALFORMED_001")
            second_extra = unexpected_symbol_block(base, result, seed=0x602, circuit_id="EXTRA_MALFORMED_002")
            malformed_extras = {
                "missing uuid": re.sub(r'\n    \(uuid "[^"]+"\)', "", extra, count=1),
                "missing at": re.sub(r'\n    \(at [^)]+\)', "", extra, count=1),
                "missing lib_id": re.sub(r'\n    \(lib_id "[^"]+"\)', "", extra, count=1),
                "malformed x": re.sub(r'\n    \(at [^)]+\)', "\n    (at NOT_A_NUMBER 10 0)", extra, count=1),
                "malformed y": re.sub(r'\n    \(at [^)]+\)', "\n    (at 10 NOT_A_NUMBER 0)", extra, count=1),
                "malformed orientation": re.sub(r'\n    \(at [^)]+\)', "\n    (at 10 10 NOT_A_ROTATION)", extra, count=1),
                "multiple malformed extras": (
                    re.sub(r'\n    \(uuid "[^"]+"\)', "", extra, count=1)
                    + re.sub(r'\n    \(at [^)]+\)', "", second_extra, count=1)
                ),
                "multiple malformed extras reversed": (
                    re.sub(r'\n    \(at [^)]+\)', "", second_extra, count=1)
                    + re.sub(r'\n    \(uuid "[^"]+"\)', "", extra, count=1)
                ),
            }
            expected_error_keys = {
                "missing uuid": "missing_symbol_uuid",
                "missing at": "missing_symbol_at",
                "missing lib_id": "missing_symbol_lib_id",
                "malformed x": "malformed_symbol_x",
                "malformed y": "malformed_symbol_y",
                "malformed orientation": "malformed_symbol_orientation",
                "multiple malformed extras": "malformed_placed_symbol_count",
                "multiple malformed extras reversed": "malformed_placed_symbol_count",
            }

            for name, malformed_block in malformed_extras.items():
                with self.subTest(name=name):
                    schematic = base.replace("\n  (symbol_instances", f"\n{malformed_block}  (symbol_instances", 1)
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)
                    self.assertFalse(check.valid)
                    self.assertTrue(any(expected_error_keys[name] in error for error in check.parse_errors))
                    self.assertTrue(any("malformed_placed_symbol_count" in error for error in check.parse_errors))

    def test_artifact_checker_rejects_expected_symbol_missing_uuid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            r_symbol = component_symbol_block(base, "R_LOAD_001")
            malformed_r_symbol = re.sub(r'\n    \(uuid "[^"]+"\)', "", r_symbol, count=1)
            schematic_path.write_text(base.replace(r_symbol, malformed_r_symbol, 1), encoding="utf-8")

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("missing_symbol_uuid" in error for error in check.parse_errors))
        self.assertTrue(any("missing placed symbol for represented component R_LOAD_001" in error for error in check.parse_errors))

    def test_placeholder_symbol_instances_receive_full_structural_validation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = unresolved_regulator_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertTrue(check.valid)
        self.assertEqual(check.parse_errors, [])
        self.assertEqual(check.generated_connectivity["NET_VIN"], ["U_REG_001:PIN_U1_IN"])

    def test_artifact_checker_detects_explicit_net_partition(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            circuit = resolved_circuit()
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            partitioned = base.replace('(global_label "NET_VIN"', '(global_label "NET_VIN_ISLAND_A"', 1).replace(
                '(global_label "NET_VIN"',
                '(global_label "NET_VIN_ISLAND_B"',
                1,
            )
            island_a = connection_point(result, "PIN_J1_1")
            island_b = connection_point(result, "PIN_R1_1")
            island_wires = "".join(
                [
                    wire_between(island_a, (island_a[0] + 10.0, island_a[1]), "00000000-0000-0000-0000-000000000401"),
                    wire_between(island_b, (island_b[0] - 10.0, island_b[1]), "00000000-0000-0000-0000-000000000402"),
                    label_at("NET_VIN", island_a, "00000000-0000-0000-0000-000000000403"),
                ]
            )
            schematic_path.write_text(insert_before_symbol_instances(partitioned, island_wires), encoding="utf-8")

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("NET_VIN" in mismatch for mismatch in check.net_mismatches))

    def test_symbol_embedding_preserves_source_subtree_quoting(self):
        special = component(
            "U_SPECIAL_001",
            "U1",
            "other",
            [
                pin("U_SPECIAL_001", "PIN_SPECIAL_A", "1", "A"),
                pin("U_SPECIAL_001", "PIN_SPECIAL_B", "2", "B"),
            ],
            role="quoted_symbol_fixture",
            symbol=symbol_ref("Special", "Symbol With Spaces"),
            footprint=footprint_ref(),
        )
        circuit = CircuitIR.model_validate(
            circuit_data(
                components=[special],
                nets=[
                    net("NET_A", "A", [{"component_instance_id": "U_SPECIAL_001", "pin_id": "PIN_SPECIAL_A"}]),
                    net("NET_B", "B", [{"component_instance_id": "U_SPECIAL_001", "pin_id": "PIN_SPECIAL_B"}]),
                ],
            )
        )

        result, files = self.generate_kicad(circuit)

        self.assertEqual(result.status, GenerationStatus.SUCCESS)
        self.assertIn('(symbol "Special:Symbol With Spaces"', files["circuit.kicad_sch"])
        self.assertIn('(symbol "Special:Symbol With Spaces_0_1"', files["circuit.kicad_sch"])
        self.assertIn('(property "Description" "Line with spaces and \\"quoted\\" text"', files["circuit.kicad_sch"])

    def test_unsupported_multi_unit_symbols_fall_back_to_placeholder(self):
        dual = component(
            "U_DUAL_001",
            "U1",
            "other",
            [
                pin("U_DUAL_001", "PIN_DUAL_A", "1", "A"),
                pin("U_DUAL_001", "PIN_DUAL_B", "2", "B"),
            ],
            role="multi_unit_fixture",
            symbol=symbol_ref("Complex", "DualUnit"),
            footprint=footprint_ref(),
        )
        circuit = CircuitIR.model_validate(
            circuit_data(
                components=[dual],
                nets=[
                    net("NET_A", "A", [{"component_instance_id": "U_DUAL_001", "pin_id": "PIN_DUAL_A"}]),
                    net("NET_B", "B", [{"component_instance_id": "U_DUAL_001", "pin_id": "PIN_DUAL_B"}]),
                ],
                status="partial",
            )
        )

        result, files = self.generate_kicad(circuit)

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertIn("SchematicAI:PLACEHOLDER_U_DUAL_001", files["circuit.kicad_sch"])
        self.assertIn(GenerationDiagnosticCategory.UNSUPPORTED_SYMBOL_VARIANT, {diagnostic.category for diagnostic in result.diagnostics})

    def test_unsupported_alternate_style_symbol_falls_back_to_placeholder(self):
        alternate = component(
            "U_ALT_001",
            "U1",
            "other",
            [pin("U_ALT_001", "PIN_ALT_A", "1", "A")],
            role="alternate_style_fixture",
            symbol=symbol_ref("Complex", "AlternateStyle"),
            footprint=footprint_ref(),
        )
        circuit = CircuitIR.model_validate(
            circuit_data(
                components=[alternate],
                nets=[net("NET_A", "A", [{"component_instance_id": "U_ALT_001", "pin_id": "PIN_ALT_A"}])],
            )
        )

        result, files = self.generate_kicad(circuit)

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertIn("SchematicAI:PLACEHOLDER_U_ALT_001", files["circuit.kicad_sch"])
        self.assertIn(
            GenerationDiagnosticCategory.UNSUPPORTED_SYMBOL_VARIANT,
            {diagnostic.category for diagnostic in result.diagnostics},
        )

    def test_artifact_checker_detects_accidental_no_connect_on_unresolved_pin(self):
        unknown = component(
            "U_UNKNOWN_001",
            "U1",
            "regulator",
            [
                pin("U_UNKNOWN_001", "PIN_UNKNOWN_IN", None, "IN", resolution="unresolved"),
                pin("U_UNKNOWN_001", "PIN_UNKNOWN_PENDING", None, "PENDING", state="unresolved", resolution="unresolved"),
            ],
            resolution="unresolved",
            implementation="partial",
        )
        circuit = CircuitIR.model_validate(
            circuit_data(
                components=[unknown],
                nets=[net("NET_VIN", "VIN", [{"component_instance_id": "U_UNKNOWN_001", "pin_id": "PIN_UNKNOWN_IN"}])],
                status="partial",
            )
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR))
            schematic_path = output_dir / "circuit.kicad_sch"
            endpoint = next(
                endpoint
                for mapping in result.manifest.object_mappings
                if mapping.source_object_id == "U_UNKNOWN_001"
                for endpoint in mapping.metadata["pin_endpoints"]
                if endpoint["circuit_pin_id"] == "PIN_UNKNOWN_PENDING"
            )
            inserted = (
                f'  (no_connect (at {endpoint["connection_point"]["x"]} {endpoint["connection_point"]["y"]})\n'
                '    (uuid "00000000-0000-0000-0000-000000000001")\n'
                "  )\n"
            )
            schematic_path.write_text(
                schematic_path.read_text(encoding="utf-8").replace("\n)\n", f"\n{inserted})\n", 1),
                encoding="utf-8",
            )

            check = KiCadArtifactChecker().check(schematic_path=schematic_path, circuit_ir=circuit, manifest=result.manifest)

        self.assertFalse(check.valid)
        self.assertTrue(any("accidental no-connect" in mismatch for mismatch in check.no_connect_mismatches))

    def test_m8_fv_001_local_label_alias_merge_is_rejected_like_global_label(self):
        circuit = resolved_circuit()
        checks = {}
        for kind, renderer in (("local", local_label_at), ("global", label_at)):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                result = KiCadBackend().generate(
                    circuit,
                    GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
                )
                self.assertEqual(result.status, GenerationStatus.SUCCESS)
                schematic_path = output_dir / "circuit.kicad_sch"
                alias = "".join(
                    [
                        renderer("UNINTENDED_ALIAS", connection_point(result, "PIN_J1_1"), "10000000-0000-0000-0000-000000000001"),
                        renderer("UNINTENDED_ALIAS", connection_point(result, "PIN_R1_2"), "10000000-0000-0000-0000-000000000002"),
                    ]
                )
                schematic_path.write_text(
                    insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), alias),
                    encoding="utf-8",
                )
                checks[kind] = KiCadArtifactChecker().check(
                    schematic_path=schematic_path,
                    circuit_ir=circuit,
                    manifest=result.manifest,
                )

        self.assertFalse(checks["local"].valid)
        self.assertFalse(checks["global"].valid)
        self.assertTrue(any("conflicting canonical labels" in item for item in checks["local"].net_mismatches))
        self.assertEqual(checks["local"].generated_connectivity, checks["global"].generated_connectivity)
        self.assertEqual(
            [item for item in checks["local"].net_mismatches if "conflicting canonical labels" in item],
            [item for item in checks["global"].net_mismatches if "conflicting canonical labels" in item],
        )

    def test_m8_fv_001_local_and_global_conflicts_are_order_independent_but_text_is_not_electrical(self):
        circuit = resolved_circuit()
        point = None
        ordered_checks = []
        for reverse in (False, True):
            with self.subTest(reverse=reverse), tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                result = KiCadBackend().generate(
                    circuit,
                    GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
                )
                self.assertEqual(result.status, GenerationStatus.SUCCESS)
                point = connection_point(result, "PIN_J1_1")
                labels = [
                    local_label_at("NET_VOUT", point, "10000000-0000-0000-0000-000000000003"),
                    label_at("NET_VIN", point, "10000000-0000-0000-0000-000000000004"),
                ]
                if reverse:
                    labels.reverse()
                schematic_path = output_dir / "circuit.kicad_sch"
                schematic_path.write_text(
                    insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), "".join(labels)),
                    encoding="utf-8",
                )
                ordered_checks.append(
                    KiCadArtifactChecker().check(
                        schematic_path=schematic_path,
                        circuit_ir=circuit,
                        manifest=result.manifest,
                    )
                )

        self.assertFalse(ordered_checks[0].valid)
        self.assertEqual(ordered_checks[0].net_mismatches, ordered_checks[1].net_mismatches)
        self.assertTrue(any("conflicting canonical labels" in item for item in ordered_checks[0].net_mismatches))

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = KiCadBackend().generate(
                circuit,
                GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )
            schematic_path = output_dir / "circuit.kicad_sch"
            annotation = annotation_text_at(
                "NET_VOUT",
                connection_point(result, "PIN_J1_1"),
                "10000000-0000-0000-0000-000000000005",
            )
            schematic_path.write_text(
                insert_before_symbol_instances(schematic_path.read_text(encoding="utf-8"), annotation),
                encoding="utf-8",
            )
            annotation_check = KiCadArtifactChecker().check(
                schematic_path=schematic_path,
                circuit_ir=circuit,
                manifest=result.manifest,
            )

        self.assertTrue(annotation_check.valid)

    def test_m8_fv_001_unsupported_or_malformed_electrical_labels_fail_closed(self):
        circuit = resolved_circuit()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = KiCadBackend().generate(
                circuit,
                GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )
            self.assertEqual(result.status, GenerationStatus.SUCCESS)
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            point = connection_point(result, "PIN_J1_1")
            unsupported = {
                "hierarchical label": (
                    f'  (hierarchical_label "NET_VIN" (shape input) (at {point[0]} {point[1]} 0)\n'
                    '    (uuid "10000000-0000-0000-0000-000000000006")\n'
                    '    (effects (font (size 1.27 1.27)))\n'
                    "  )\n"
                ),
                "netclass flag": (
                    f'  (netclass_flag "Default" (length 2.54) (shape round) (at {point[0]} {point[1]} 0)\n'
                    '    (uuid "10000000-0000-0000-0000-000000000007")\n'
                    '    (effects (font (size 1.27 1.27)))\n'
                    "  )\n"
                ),
                "malformed local label": (
                    '  (label "NET_VIN"\n'
                    '    (uuid "10000000-0000-0000-0000-000000000008")\n'
                    '    (effects (font (size 1.27 1.27)))\n'
                    "  )\n"
                ),
            }
            for name, block in unsupported.items():
                with self.subTest(name=name):
                    schematic_path.write_text(insert_before_symbol_instances(base, block), encoding="utf-8")
                    check = KiCadArtifactChecker().check(
                        schematic_path=schematic_path,
                        circuit_ir=circuit,
                        manifest=result.manifest,
                    )
                    self.assertFalse(check.valid)
                    self.assertTrue(check.parse_errors)

    def test_m8_fv_002_unresolved_pin_electrical_attachments_are_rejected(self):
        circuit = circuit_with_placeholder_unresolved_pin()
        mutations = {
            "wire": lambda result: wire_between(
                connection_point(result, "PIN_UNKNOWN_PENDING"),
                connection_point(result, "PIN_UNKNOWN_IN"),
                "20000000-0000-0000-0000-000000000001",
            ),
            "local label": lambda result: local_label_at(
                "NET_IN",
                connection_point(result, "PIN_UNKNOWN_PENDING"),
                "20000000-0000-0000-0000-000000000002",
            ),
            "global label": lambda result: label_at(
                "NET_IN",
                connection_point(result, "PIN_UNKNOWN_PENDING"),
                "20000000-0000-0000-0000-000000000003",
            ),
            "no-connect": lambda result: no_connect_at(
                connection_point(result, "PIN_UNKNOWN_PENDING"),
                "20000000-0000-0000-0000-000000000004",
            ),
        }
        for name, make_mutation in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                result = KiCadBackend().generate(
                    circuit,
                    GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
                )
                self.assertEqual(result.status, GenerationStatus.PARTIAL)
                schematic_path = output_dir / "circuit.kicad_sch"
                schematic_path.write_text(
                    insert_before_symbol_instances(
                        schematic_path.read_text(encoding="utf-8"),
                        make_mutation(result),
                    ),
                    encoding="utf-8",
                )
                check = KiCadArtifactChecker().check(
                    schematic_path=schematic_path,
                    circuit_ir=circuit,
                    manifest=result.manifest,
                )
                self.assertFalse(check.valid)
                self.assertTrue(
                    any("unresolved pin" in item for item in [*check.net_mismatches, *check.no_connect_mismatches])
                )

    def test_m8_fv_003_raw_no_connect_markers_are_one_to_one_and_well_formed(self):
        circuit = circuit_with_expected_no_connect()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = KiCadBackend().generate(
                circuit,
                GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )
            self.assertEqual(result.status, GenerationStatus.SUCCESS)
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            valid_check = KiCadArtifactChecker().check(
                schematic_path=schematic_path,
                circuit_ir=circuit,
                manifest=result.manifest,
            )
            self.assertTrue(valid_check.valid)
            nc_point = connection_point(result, "PIN_J1_2")
            self.assertEqual(base.count(f"(no_connect (at {nc_point[0]:g} {nc_point[1]:g})"), 1)
            connected_point = connection_point(result, "PIN_J1_1")
            malformed = '  (no_connect (at "bad" 1) (uuid "30000000-0000-0000-0000-000000000005"))\n'
            mutations = {
                "orphan with no expected endpoint": insert_before_symbol_instances(
                    base,
                    no_connect_at((999.0, 999.0), "30000000-0000-0000-0000-000000000001"),
                ),
                "duplicate at expected endpoint": insert_before_symbol_instances(
                    base,
                    no_connect_at(nc_point, "30000000-0000-0000-0000-000000000002"),
                ),
                "marker at connected pin": insert_before_symbol_instances(
                    base,
                    no_connect_at(connected_point, "30000000-0000-0000-0000-000000000003"),
                ),
                "misplaced marker near expected endpoint": base.replace(
                    f"(no_connect (at {nc_point[0]:g} {nc_point[1]:g})",
                    f"(no_connect (at {nc_point[0] + 0.01:g} {nc_point[1]:g})",
                    1,
                ),
                "malformed marker": insert_before_symbol_instances(base, malformed),
                "all expected plus extra orphan": insert_before_symbol_instances(
                    base,
                    no_connect_at((998.0, 998.0), "30000000-0000-0000-0000-000000000006"),
                ),
            }
            for name, schematic in mutations.items():
                with self.subTest(name=name):
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(
                        schematic_path=schematic_path,
                        circuit_ir=circuit,
                        manifest=result.manifest,
                    )
                    self.assertFalse(check.valid)

    def test_m8_fv_004_document_parser_rejects_multiple_top_level_expressions_and_atoms(self):
        circuit = resolved_circuit()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = KiCadBackend().generate(
                circuit,
                GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )
            schematic_path = output_dir / "circuit.kicad_sch"
            base = schematic_path.read_text(encoding="utf-8")
            invalid_documents = {
                "leading expression": "(extra value)\n" + base,
                "trailing expression": base + "(extra value)\n",
                "leading atom": "foo\n" + base,
                "trailing atom": base + "foo\n",
                "two schematic roots": base + base,
            }
            for name, schematic in invalid_documents.items():
                with self.subTest(name=name):
                    schematic_path.write_text(schematic, encoding="utf-8")
                    check = KiCadArtifactChecker().check(
                        schematic_path=schematic_path,
                        circuit_ir=circuit,
                        manifest=result.manifest,
                    )
                    self.assertFalse(check.valid)
                    self.assertTrue(check.parse_errors)

        self.assertEqual(parse_sexpr("(kicad_sch (nested (child value)))")[0], "kicad_sch")
        for malformed in ("(kicad_sch", '(kicad_sch "unterminated)'):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    parse_sexpr(malformed)

    def test_m8_fv_005_supported_real_symbol_keeps_unresolved_pin_structurally_present(self):
        circuit = circuit_with_supported_real_unresolved_pin()
        result, files = self.generate_kicad(circuit)

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertTrue(result.manifest.metadata["artifact_check"]["valid"])
        self.assertEqual(result.manifest.placeholders, [])
        self.assertIn('(lib_id "Device:R")', files["circuit.kicad_sch"])
        placed = component_symbol_block(files["circuit.kicad_sch"], "R_LOAD_001")
        self.assertIn('(pin "1"', placed)
        self.assertIn('(pin "2"', placed)
        endpoint = endpoint_for(result, "PIN_R1_PENDING")
        self.assertEqual(endpoint["kicad_pin_number"], "2")

        pin_point = endpoint["connection_point"]
        self.assertNotIn(f'(global_label "NET_IN"\n    (shape input)\n    (at {pin_point["x"]} {pin_point["y"]}', files["circuit.kicad_sch"])
        self.assertNotIn(f'(no_connect (at {pin_point["x"]} {pin_point["y"]})', files["circuit.kicad_sch"])

    def test_m8_fv_005_supported_real_unresolved_pin_corruption_is_rejected(self):
        circuit = circuit_with_supported_real_unresolved_pin()
        mutations = {
            "wire": lambda result: wire_between(
                connection_point(result, "PIN_R1_PENDING"),
                connection_point(result, "PIN_R1_1"),
                "50000000-0000-0000-0000-000000000001",
            ),
            "local label": lambda result: local_label_at(
                "NET_IN",
                connection_point(result, "PIN_R1_PENDING"),
                "50000000-0000-0000-0000-000000000002",
            ),
            "global label": lambda result: label_at(
                "NET_IN",
                connection_point(result, "PIN_R1_PENDING"),
                "50000000-0000-0000-0000-000000000003",
            ),
            "no-connect": lambda result: no_connect_at(
                connection_point(result, "PIN_R1_PENDING"),
                "50000000-0000-0000-0000-000000000004",
            ),
        }
        for name, make_mutation in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                result = KiCadBackend().generate(
                    circuit,
                    GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
                )
                self.assertEqual(result.status, GenerationStatus.PARTIAL)
                self.assertTrue(result.manifest.metadata["artifact_check"]["valid"])
                schematic_path = output_dir / "circuit.kicad_sch"
                schematic_path.write_text(
                    insert_before_symbol_instances(
                        schematic_path.read_text(encoding="utf-8"),
                        make_mutation(result),
                    ),
                    encoding="utf-8",
                )
                check = KiCadArtifactChecker().check(
                    schematic_path=schematic_path,
                    circuit_ir=circuit,
                    manifest=result.manifest,
                )
                self.assertFalse(check.valid)
                self.assertTrue(
                    any("unresolved pin" in item for item in [*check.net_mismatches, *check.no_connect_mismatches])
                )

    def test_generation_status_is_gated_by_artifact_checker(self):
        class RejectingChecker:
            def check(self, *, schematic_path, circuit_ir, manifest):
                return KiCadArtifactChecker().check(
                    schematic_path=schematic_path,
                    circuit_ir=circuit_ir,
                    manifest=manifest.model_copy(update={"object_mappings": []}),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = KiCadBackend(artifact_checker=RejectingChecker()).generate(
                resolved_circuit(),
                GenerationContext(output_dir=Path(temp_dir), kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )

        self.assertEqual(result.status, GenerationStatus.FAILED)
        self.assertIn(GenerationDiagnosticCategory.ARTIFACT_CHECK_FAILED, {diagnostic.category for diagnostic in result.diagnostics})

    def test_generation_status_fails_when_symbol_instance_structure_is_corrupted(self):
        class RemovingPinsChecker:
            def check(self, *, schematic_path, circuit_ir, manifest):
                path = Path(schematic_path)
                path.write_text(remove_all_placed_pin_records(path.read_text(encoding="utf-8")), encoding="utf-8")
                return KiCadArtifactChecker().check(schematic_path=path, circuit_ir=circuit_ir, manifest=manifest)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = KiCadBackend(artifact_checker=RemovingPinsChecker()).generate(
                resolved_circuit(),
                GenerationContext(output_dir=Path(temp_dir), kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )

        self.assertEqual(result.status, GenerationStatus.FAILED)
        self.assertIn(GenerationDiagnosticCategory.ARTIFACT_CHECK_FAILED, {diagnostic.category for diagnostic in result.diagnostics})

    def test_generation_and_manifest_fail_when_expected_symbol_uuid_is_missing(self):
        class RemovingSymbolUuidChecker:
            def check(self, *, schematic_path, circuit_ir, manifest):
                path = Path(schematic_path)
                schematic = path.read_text(encoding="utf-8")
                symbol = component_symbol_block(schematic, "R_LOAD_001")
                malformed = re.sub(r'\n    \(uuid "[^"]+"\)', "", symbol, count=1)
                path.write_text(schematic.replace(symbol, malformed, 1), encoding="utf-8")
                return KiCadArtifactChecker().check(schematic_path=path, circuit_ir=circuit_ir, manifest=manifest)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = KiCadBackend(artifact_checker=RemovingSymbolUuidChecker()).generate(
                resolved_circuit(),
                GenerationContext(output_dir=Path(temp_dir), kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )

        self.assertEqual(result.status, GenerationStatus.FAILED)
        self.assertEqual(result.manifest.generation_status, GenerationStatus.FAILED)
        self.assertFalse(result.manifest.metadata["artifact_check"]["valid"])

    def test_generation_fails_when_component_cannot_be_safely_represented(self):
        broken = component(
            "U_UNKNOWN_001",
            "U1",
            "other",
            [],
            resolution="unresolved",
            implementation="unresolved",
        )
        circuit = CircuitIR.model_validate(circuit_data(components=[broken], nets=[], status="partial"))
        with tempfile.TemporaryDirectory() as temp_dir:
            result = KiCadBackend().generate(circuit, GenerationContext(output_dir=Path(temp_dir)))

        self.assertEqual(result.status, GenerationStatus.FAILED)
        self.assertEqual(result.generated_files, [])
        self.assertIn(GenerationDiagnosticCategory.UNSUPPORTED_FEATURE, {diagnostic.category for diagnostic in result.diagnostics})

    def test_resolvers_keep_symbol_footprint_and_pin_mapping_boundaries_separate(self):
        circuit = resolved_circuit()
        resistor = next(component for component in circuit.components if component.instance_id == "R_LOAD_001")

        self.assertFalse(SymbolResolver().resolve(resistor).requires_placeholder)
        self.assertIsNotNone(FootprintResolver().resolve(resistor).footprint_reference)
        self.assertTrue(PinMappingResolver().resolve(resistor, SymbolResolver().resolve(resistor)).is_trusted)

    def test_layout_is_deterministic(self):
        layout_a = SchematicLayoutStrategy().layout(resolved_circuit())
        layout_b = SchematicLayoutStrategy().layout(resolved_circuit())

        self.assertEqual(layout_a, layout_b)
        self.assertEqual(set(layout_a.component_placements), {"J_IN_001", "R_LOAD_001", "C_OUT_001"})

    def test_python_representation_backend_generates_optional_one_way_representation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = PythonCircuitRepresentationBackend().generate(unresolved_regulator_circuit(), GenerationContext(output_dir=Path(temp_dir)))
            source = (Path(temp_dir) / "circuit.py").read_text(encoding="utf-8")

        self.assertEqual(result.status, GenerationStatus.PARTIAL)
        self.assertFalse(result.capabilities.supports_round_trip)
        self.assertIn("CIRCUITIR_PYTHON_REPRESENTATION", source)
        self.assertIn('"canonical_source": "CircuitIR"', source)

    def test_optional_kicad_cli_netlist_export_when_available(self):
        kicad_cli = shutil.which("kicad-cli")
        if kicad_cli is None:
            self.skipTest("kicad-cli is not available on PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = KiCadBackend().generate(
                resolved_circuit(),
                GenerationContext(output_dir=output_dir, kicad_symbol_dir=FIXTURE_SYMBOL_DIR),
            )
            self.assertEqual(result.status, GenerationStatus.SUCCESS)
            completed = subprocess.run(
                [
                    kicad_cli,
                    "sch",
                    "export",
                    "netlist",
                    "--output",
                    str(output_dir / "circuit.net"),
                    "--format",
                    "kicadsexpr",
                    str(output_dir / "circuit.kicad_sch"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
