"""Optional Python circuit representation generated from CircuitIR."""

from __future__ import annotations

import json

from schematic_ai.application.eda.backend import EDABackend, file_sha256, relative_artifact_path
from schematic_ai.application.eda.models import (
    BackendCapabilities,
    EDA_BACKEND_VERSION,
    GeneratedArtifactFormat,
    GeneratedArtifactManifest,
    GeneratedArtifactType,
    GeneratedFile,
    GenerationContext,
    GenerationDiagnostic,
    GenerationResult,
    GenerationStatus,
    ObjectMapping,
)
from schematic_ai.domain.circuit_ir import CircuitIR, PinConnectionState


class PythonCircuitRepresentationBackend(EDABackend):
    """Generate a deterministic Python representation without claiming SKiDL semantics."""

    name = "python_circuit_representation"

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            backend=self.name,
            backend_version=EDA_BACKEND_VERSION,
            target_version=None,
            supports_schematic=False,
            supports_footprints=False,
            supports_placeholders=True,
            supports_partial_circuit=True,
            deterministic_generation=True,
            supports_round_trip=False,
            supported_formats=["python", "json"],
        )

    def generate(self, circuit_ir: CircuitIR, context: GenerationContext) -> GenerationResult:
        circuit_ir = CircuitIR.model_validate_json(circuit_ir.model_dump_json())
        context.output_dir.mkdir(parents=True, exist_ok=True)

        path = context.output_dir / f"{context.artifact_basename}.py"
        path.write_text(self._render_source(circuit_ir), encoding="utf-8")
        generated_file = GeneratedFile(
            artifact_type=GeneratedArtifactType.PYTHON_CIRCUIT_REPRESENTATION,
            path=relative_artifact_path(path, context.output_dir),
            format=GeneratedArtifactFormat.PYTHON,
            checksum=file_sha256(path),
            metadata={"canonical_source": "CircuitIR"},
        )
        mappings = [
            ObjectMapping(
                source_object_id=component.instance_id,
                source_object_type="component_instance",
                backend_object_id=f"python_part:{component.reference_designator or component.instance_id}",
                backend_object_type="python_component_record",
                artifact_type=GeneratedArtifactType.PYTHON_CIRCUIT_REPRESENTATION,
                metadata={"round_trip": False},
            )
            for component in circuit_ir.components
        ]
        unresolved = [
            component.instance_id
            for component in circuit_ir.components
            if component.resolution_status != "resolved" or any(pin.connection_state == PinConnectionState.UNRESOLVED for pin in component.pins)
        ]
        status = GenerationStatus.PARTIAL if unresolved or circuit_ir.implementation_status != "resolved" else GenerationStatus.SUCCESS
        manifest = GeneratedArtifactManifest(
            manifest_id=f"MANIFEST_{circuit_ir.circuit_id}_REV_{circuit_ir.revision}_PYTHON_REPRESENTATION",
            source_circuit_id=circuit_ir.circuit_id,
            source_circuit_revision=circuit_ir.revision,
            backend=self.name,
            backend_version=EDA_BACKEND_VERSION,
            generated_files=[generated_file],
            object_mappings=mappings,
            placeholders=[],
            unresolved_objects=unresolved,
            warnings=[],
            errors=[],
            generation_status=status,
            metadata={
                "round_trip": False,
                "connectivity": {
                    net.net_id: [connection.model_dump(mode="json") for connection in net.connections]
                    for net in circuit_ir.nets
                },
            },
        )
        return GenerationResult(
            status=status,
            backend=self.name,
            capabilities=self.capabilities(),
            manifest=manifest,
            generated_files=[generated_file],
            diagnostics=[],
        )

    def _render_source(self, circuit_ir: CircuitIR) -> str:
        payload = {
            "source_circuit_id": circuit_ir.circuit_id,
            "source_circuit_revision": circuit_ir.revision,
            "canonical_source": "CircuitIR",
            "round_trip": False,
            "components": [
                {
                    "instance_id": component.instance_id,
                    "ref": component.reference_designator,
                    "value": component.value.model_dump(mode="json") if component.value else None,
                    "symbol": (
                        f"{component.symbol_reference.library}:{component.symbol_reference.symbol_name}"
                        if component.symbol_reference and component.symbol_reference.verified_exists
                        else None
                    ),
                    "placeholder": component.symbol_reference is None or not component.symbol_reference.verified_exists,
                    "pins": [pin.model_dump(mode="json") for pin in component.pins],
                }
                for component in circuit_ir.components
            ],
            "nets": [
                {
                    "net_id": net.net_id,
                    "name": net.name or net.net_id,
                    "connections": [connection.model_dump(mode="json") for connection in net.connections],
                }
                for net in circuit_ir.nets
            ],
        }
        return "\n".join(
            [
                '"""Generated Python circuit representation.',
                "",
                "CircuitIR remains the canonical electrical state. This file is a",
                "derived one-way artifact and external edits do not update CircuitIR.",
                '"""',
                "",
                "import json",
                "",
                "CIRCUITIR_PYTHON_REPRESENTATION = json.loads(",
                "    r'''",
                json.dumps(payload, indent=2, sort_keys=True),
                "'''",
                ")",
                "",
            ]
        )


SKiDLBackend = PythonCircuitRepresentationBackend
