from __future__ import annotations

from pathlib import Path

from schematic_ai.application.eda import GenerationContext, KiCadBackend
from schematic_ai.domain.circuit_ir import CircuitIR


ROOT = Path(__file__).resolve().parents[1]
CIRCUIT_IR_PATH = ROOT / "examples" / "circuit_ir_v0_1.json"
OUTPUT_DIR = ROOT / "generated" / "milestone_8"
KICAD_SYMBOL_FIXTURE_DIR = ROOT / "examples" / "kicad9_symbols"


def milestone_8_demo_circuit() -> CircuitIR:
    """Use the frozen CircuitIR example with one trusted synthetic CAD mapping."""

    data = CircuitIR.model_validate_json(CIRCUIT_IR_PATH.read_text(encoding="utf-8")).model_dump(mode="json")
    for component in data["components"]:
        if component["instance_id"] == "C_IN_001":
            component["resolution_status"] = "resolved"
            component["component_record_id"] = "CMP_SYNTHETIC_CAPACITOR_22UF"
            component["implementation_status"] = "resolved"
            component["symbol_reference"] = {
                "library": "Device",
                "symbol_name": "C",
                "source_id": "SRC_KICAD_001",
                "verified_exists": True,
                "metadata": component["metadata"],
            }
            component["footprint_reference"] = None
            for pin in component["pins"]:
                pin["resolution_status"] = "resolved"
    return CircuitIR.model_validate(data)


def main() -> None:
    circuit_ir = milestone_8_demo_circuit()
    result = KiCadBackend().generate(
        circuit_ir,
        GenerationContext(
            output_dir=OUTPUT_DIR,
            artifact_basename="circuit",
            include_python_representation=True,
            kicad_symbol_dir=KICAD_SYMBOL_FIXTURE_DIR,
        ),
    )
    print(
        f"Generated Milestone 8 EDA artifacts for {circuit_ir.circuit_id} revision {circuit_ir.revision}: "
        f"{result.status}"
    )
    for generated_file in result.generated_files:
        print(f"- {OUTPUT_DIR / generated_file.path}")
    if result.diagnostics:
        print("Diagnostics:")
        for diagnostic in result.diagnostics:
            print(f"- {diagnostic.severity}: {diagnostic.category}: {diagnostic.source_object_id}: {diagnostic.message}")


if __name__ == "__main__":
    main()
