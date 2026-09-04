"""Direct KiCad schematic backend for CircuitIR v0.1."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from schematic_ai.application.eda.backend import EDABackend, file_sha256, relative_artifact_path
from schematic_ai.application.eda.checker import KiCadArtifactChecker, transform_point
from schematic_ai.application.eda.errors import ArtifactWriteError
from schematic_ai.application.eda.layout import ComponentPlacement, SchematicLayout, SchematicLayoutStrategy
from schematic_ai.application.eda.models import (
    ArtifactCheckResult,
    BackendCapabilities,
    EDA_BACKEND_VERSION,
    GeneratedArtifactFormat,
    GeneratedArtifactManifest,
    GeneratedArtifactType,
    GeneratedFile,
    GeneratedPinEndpoint,
    GenerationContext,
    GenerationDiagnostic,
    GenerationDiagnosticCategory,
    GenerationDiagnosticSeverity,
    GenerationResult,
    GenerationStatus,
    ObjectMapping,
    PlaceholderRecord,
)
from schematic_ai.application.eda.resolvers import (
    FootprintResolver,
    PinMappingResolver,
    SymbolResolution,
    SymbolResolver,
)
from schematic_ai.application.eda.symbols import KiCadSymbolDefinition, KiCadSymbolDefinitionResolver
from schematic_ai.domain.circuit_ir import (
    CircuitIR,
    ComponentInstance,
    ComponentResolutionStatus,
    PinConnectionState,
)
from schematic_ai.domain.circuit_ir.models import CircuitValue


KICAD_TARGET_VERSION = "9"
KICAD_FILE_VERSION = "20250114"
KICAD_NAMESPACE = uuid.UUID("b2d750e3-33db-45dc-b408-300602fca743")


class KiCadBackend(EDABackend):
    name = "kicad"

    def __init__(
        self,
        *,
        symbol_resolver: SymbolResolver | None = None,
        footprint_resolver: FootprintResolver | None = None,
        pin_mapping_resolver: PinMappingResolver | None = None,
        layout_strategy: SchematicLayoutStrategy | None = None,
        symbol_definition_resolver: KiCadSymbolDefinitionResolver | None = None,
        artifact_checker: KiCadArtifactChecker | None = None,
    ) -> None:
        self.symbol_resolver = symbol_resolver or SymbolResolver()
        self.footprint_resolver = footprint_resolver or FootprintResolver()
        self.pin_mapping_resolver = pin_mapping_resolver or PinMappingResolver()
        self.layout_strategy = layout_strategy or SchematicLayoutStrategy()
        self.symbol_definition_resolver = symbol_definition_resolver or KiCadSymbolDefinitionResolver()
        self.artifact_checker = artifact_checker or KiCadArtifactChecker()

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            backend=self.name,
            backend_version=EDA_BACKEND_VERSION,
            target_version=KICAD_TARGET_VERSION,
            supports_schematic=True,
            supports_footprints=True,
            supports_placeholders=True,
            supports_partial_circuit=True,
            deterministic_generation=True,
            supports_round_trip=False,
            supported_formats=["kicad_sch", "json"],
        )

    def generate(self, circuit_ir: CircuitIR, context: GenerationContext) -> GenerationResult:
        diagnostics: list[GenerationDiagnostic] = []
        mappings: list[ObjectMapping] = []
        placeholders: list[PlaceholderRecord] = []
        unresolved: list[str] = []
        generated_files: list[GeneratedFile] = []

        try:
            # Re-run frozen structural validation through the existing Pydantic model.
            circuit_ir = CircuitIR.model_validate_json(circuit_ir.model_dump_json())
            context.output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - defensive boundary
            diagnostic = self._diagnostic(
                "INVALID_CIRCUIT",
                GenerationDiagnosticSeverity.ERROR,
                GenerationDiagnosticCategory.INVALID_CIRCUIT,
                f"CircuitIR cannot be structurally validated: {exc}",
                circuit_ir.circuit_id if isinstance(circuit_ir, CircuitIR) else None,
            )
            manifest = self._manifest(circuit_ir, GenerationStatus.FAILED, [], [], [], [], [], [diagnostic], {})
            return GenerationResult(
                status=GenerationStatus.FAILED,
                backend=self.name,
                capabilities=self.capabilities(),
                manifest=manifest,
                diagnostics=[diagnostic],
            )

        layout = self.layout_strategy.layout(circuit_ir)
        component_views: list[dict[str, Any]] = []

        for component in circuit_ir.components:
            symbol_resolution = self.symbol_resolver.resolve(component)
            footprint_resolution = self.footprint_resolver.resolve(component)
            symbol_definition: KiCadSymbolDefinition | None = None
            if not symbol_resolution.requires_placeholder and symbol_resolution.symbol_reference is not None:
                symbol_definition = self.symbol_definition_resolver.resolve(
                    symbol_resolution.symbol_reference,
                    context.kicad_symbol_dir,
                )
                if symbol_definition is None:
                    symbol_failure = self.symbol_definition_resolver.last_failure_reason
                    category = (
                        GenerationDiagnosticCategory.UNSUPPORTED_SYMBOL_VARIANT
                        if symbol_failure and symbol_failure.startswith("unsupported")
                        else GenerationDiagnosticCategory.MISSING_SYMBOL
                    )
                    diagnostics.append(
                        self._diagnostic(
                            f"MISSING_SYMBOL_DEFINITION_{component.instance_id}",
                            GenerationDiagnosticSeverity.WARNING,
                            category,
                            symbol_failure or "verified symbol reference could not be loaded from configured KiCad symbol library",
                            component.instance_id,
                        )
                    )
                    symbol_resolution = SymbolResolution(
                        None,
                        True,
                        "verified symbol source definition unavailable for endpoint derivation",
                    )
            pin_mapping = self.pin_mapping_resolver.resolve(component, symbol_resolution)

            if footprint_resolution.footprint_reference is None and not symbol_resolution.requires_placeholder:
                diagnostics.append(
                    self._diagnostic(
                        f"MISSING_FOOTPRINT_{component.instance_id}",
                        GenerationDiagnosticSeverity.WARNING,
                        GenerationDiagnosticCategory.MISSING_FOOTPRINT,
                        footprint_resolution.reason or "component footprint is unresolved",
                        component.instance_id,
                    )
                )
                unresolved.append(component.instance_id)

            if not pin_mapping.is_trusted:
                diagnostics.append(
                    self._diagnostic(
                        f"UNRESOLVED_PIN_MAPPING_{component.instance_id}",
                        GenerationDiagnosticSeverity.WARNING,
                        GenerationDiagnosticCategory.UNRESOLVED_PIN_MAPPING,
                        pin_mapping.reason or "component pin mapping is not trusted",
                        component.instance_id,
                    )
                )
                symbol_resolution = SymbolResolution(None, True, pin_mapping.reason or "exact pin mapping unavailable")
                symbol_definition = None
                pin_mapping = self.pin_mapping_resolver.resolve(component, symbol_resolution)

            if symbol_resolution.requires_placeholder:
                if not context.allow_placeholders:
                    diagnostics.append(
                        self._diagnostic(
                            f"PLACEHOLDER_DISABLED_{component.instance_id}",
                            GenerationDiagnosticSeverity.ERROR,
                            GenerationDiagnosticCategory.MISSING_SYMBOL,
                            symbol_resolution.reason or "placeholder required but disabled",
                            component.instance_id,
                        )
                    )
                    continue
                if not component.pins:
                    diagnostics.append(
                        self._diagnostic(
                            f"UNREPRESENTABLE_{component.instance_id}",
                            GenerationDiagnosticSeverity.ERROR,
                            GenerationDiagnosticCategory.UNSUPPORTED_FEATURE,
                            "component cannot be represented safely because it has no known CircuitIR pins",
                            component.instance_id,
                        )
                    )
                    continue
                diagnostics.append(
                    self._diagnostic(
                        f"PLACEHOLDER_GENERATED_{component.instance_id}",
                        GenerationDiagnosticSeverity.INFO,
                        GenerationDiagnosticCategory.PLACEHOLDER_GENERATED,
                        symbol_resolution.reason or "placeholder generated",
                        component.instance_id,
                    )
                )
                if component.resolution_status == ComponentResolutionStatus.RESOLVED:
                    diagnostics.append(
                        self._diagnostic(
                            f"MISSING_SYMBOL_{component.instance_id}",
                            GenerationDiagnosticSeverity.WARNING,
                            GenerationDiagnosticCategory.MISSING_SYMBOL,
                            symbol_resolution.reason or "resolved component has no verified symbol",
                            component.instance_id,
                        )
                    )
                unresolved.append(component.instance_id)
                placeholders.append(self._placeholder_record(component, pin_mapping.pin_numbers_by_pin_id, symbol_resolution))

            backend_object_id = self._component_uuid(component.instance_id)
            pin_endpoints = self._pin_endpoints(
                component=component,
                symbol_resolution=symbol_resolution,
                pin_numbers_by_pin_id=pin_mapping.pin_numbers_by_pin_id,
                placement=layout.component_placements[component.instance_id],
                symbol_uuid=backend_object_id,
                symbol_definition=symbol_definition,
            )
            endpoint_pin_ids = {endpoint.circuit_pin_id for endpoint in pin_endpoints}
            required_endpoint_pin_ids = {
                pin.pin_id
                for pin in component.pins
                if pin.connection_state in {PinConnectionState.CONNECTED, PinConnectionState.NO_CONNECT}
            }
            missing_endpoint_pin_ids = sorted(required_endpoint_pin_ids - endpoint_pin_ids)
            if missing_endpoint_pin_ids and not symbol_resolution.requires_placeholder and context.allow_placeholders:
                diagnostics.append(
                    self._diagnostic(
                        f"UNRESOLVED_PIN_ENDPOINT_{component.instance_id}",
                        GenerationDiagnosticSeverity.WARNING,
                        GenerationDiagnosticCategory.UNRESOLVED_PIN_MAPPING,
                        f"trusted symbol definition lacks required pin endpoints: {', '.join(missing_endpoint_pin_ids)}",
                        component.instance_id,
                    )
                )
                symbol_resolution = SymbolResolution(None, True, "trusted symbol definition does not cover all required CircuitIR pins")
                symbol_definition = None
                pin_mapping = self.pin_mapping_resolver.resolve(component, symbol_resolution)
                pin_endpoints = self._pin_endpoints(
                    component=component,
                    symbol_resolution=symbol_resolution,
                    pin_numbers_by_pin_id=pin_mapping.pin_numbers_by_pin_id,
                    placement=layout.component_placements[component.instance_id],
                    symbol_uuid=backend_object_id,
                    symbol_definition=symbol_definition,
                )
                endpoint_pin_ids = {endpoint.circuit_pin_id for endpoint in pin_endpoints}
                missing_endpoint_pin_ids = sorted(required_endpoint_pin_ids - endpoint_pin_ids)
                unresolved.append(component.instance_id)
                placeholders.append(self._placeholder_record(component, pin_mapping.pin_numbers_by_pin_id, symbol_resolution))
            if missing_endpoint_pin_ids:
                diagnostics.append(
                    self._diagnostic(
                        f"MISSING_PIN_ENDPOINT_{component.instance_id}",
                        GenerationDiagnosticSeverity.ERROR,
                        GenerationDiagnosticCategory.UNRESOLVED_PIN_MAPPING,
                        f"cannot derive exact generated endpoint for pins: {', '.join(missing_endpoint_pin_ids)}",
                        component.instance_id,
                    )
                )
            mappings.append(
                ObjectMapping(
                    source_object_id=component.instance_id,
                    source_object_type="component_instance",
                    backend_object_id=backend_object_id,
                    backend_object_type="kicad_symbol",
                    artifact_type=GeneratedArtifactType.KICAD_SCHEMATIC,
                    metadata={
                        "reference_designator": self._reference_designator(component),
                        "placeholder": symbol_resolution.requires_placeholder,
                        "lib_id": self._placed_lib_id(component, symbol_resolution),
                        "pin_endpoints": [endpoint.model_dump(mode="json") for endpoint in pin_endpoints],
                        "symbol_source": (
                            str(symbol_definition.source_path)
                            if symbol_definition is not None
                            else None
                        ),
                    },
                )
            )
            component_views.append(
                {
                    "circuit_ir": circuit_ir,
                    "component": component,
                    "symbol_resolution": symbol_resolution,
                    "footprint_resolution": footprint_resolution,
                    "pin_numbers_by_pin_id": pin_mapping.pin_numbers_by_pin_id,
                    "pin_endpoints": pin_endpoints,
                    "symbol_definition": symbol_definition,
                    "placement": layout.component_placements[component.instance_id],
                    "backend_object_id": backend_object_id,
                }
            )

        for net in circuit_ir.nets:
            mappings.append(
                ObjectMapping(
                    source_object_id=net.net_id,
                    source_object_type="net",
                    backend_object_id=f"kicad_net_label:{self._net_presentation_name(net.net_id, net.name)}",
                    backend_object_type="kicad_label",
                    artifact_type=GeneratedArtifactType.KICAD_SCHEMATIC,
                    metadata={
                        "connection_count": len(net.connections),
                        "net_label": self._net_presentation_name(net.net_id, net.name),
                        "display_name": net.name,
                    },
                )
            )

        errors = [diag for diag in diagnostics if diag.severity == GenerationDiagnosticSeverity.ERROR]
        if errors:
            status = GenerationStatus.FAILED
            manifest = self._manifest(
                circuit_ir,
                status,
                [],
                mappings,
                placeholders,
                sorted(set(unresolved)),
                [diag for diag in diagnostics if diag.severity != GenerationDiagnosticSeverity.ERROR],
                errors,
                self._semantic_metadata(circuit_ir, layout),
            )
            return GenerationResult(
                status=status,
                backend=self.name,
                capabilities=self.capabilities(),
                manifest=manifest,
                diagnostics=diagnostics,
            )

        status = GenerationStatus.PARTIAL if placeholders or unresolved or diagnostics or circuit_ir.implementation_status != "resolved" else GenerationStatus.SUCCESS

        schematic_text = self._render_schematic(circuit_ir, layout, component_views)
        schematic_path = context.output_dir / f"{context.artifact_basename}.kicad_sch"
        try:
            schematic_path.write_text(schematic_text, encoding="utf-8")
        except OSError as exc:  # pragma: no cover - difficult to trigger portably
            raise ArtifactWriteError(f"failed to write {schematic_path}: {exc}") from exc

        generated_files.append(
            GeneratedFile(
                artifact_type=GeneratedArtifactType.KICAD_SCHEMATIC,
                path=relative_artifact_path(schematic_path, context.output_dir),
                format=GeneratedArtifactFormat.KICAD_SCH,
                checksum=file_sha256(schematic_path),
                metadata={"target_version": KICAD_TARGET_VERSION},
            )
        )

        if context.include_python_representation or context.include_skidl:
            from schematic_ai.application.eda.skidl import PythonCircuitRepresentationBackend

            python_result = PythonCircuitRepresentationBackend().generate(circuit_ir, context.model_copy(update={"write_manifest": False}))
            generated_files.extend(python_result.generated_files)

        manifest = self._manifest(
            circuit_ir,
            status,
            generated_files,
            mappings,
            placeholders,
            sorted(set(unresolved)),
            [diag for diag in diagnostics if diag.severity != GenerationDiagnosticSeverity.ERROR],
            [],
            self._semantic_metadata(circuit_ir, layout),
        )
        check_result = self.artifact_checker.check(
            schematic_path=schematic_path,
            circuit_ir=circuit_ir,
            manifest=manifest,
        )
        diagnostics.extend(check_result.diagnostics)
        if not check_result.valid:
            status = GenerationStatus.FAILED
        elif placeholders or unresolved or diagnostics or circuit_ir.implementation_status != "resolved":
            status = GenerationStatus.PARTIAL
        else:
            status = GenerationStatus.SUCCESS
        check_errors = [diag for diag in diagnostics if diag.severity == GenerationDiagnosticSeverity.ERROR]
        manifest = self._manifest(
            circuit_ir,
            status,
            generated_files,
            mappings,
            placeholders,
            sorted(set(unresolved)),
            [diag for diag in diagnostics if diag.severity != GenerationDiagnosticSeverity.ERROR],
            check_errors,
            {
                **self._semantic_metadata(circuit_ir, layout),
                "artifact_check": check_result.model_dump(mode="json"),
            },
        )

        if context.write_diagnostic_report:
            report_path = context.output_dir / "generation_report.json"
            report_payload = {
                "status": status,
                "backend": self.name,
                "diagnostics": [diag.model_dump(mode="json") for diag in diagnostics],
                "semantic_checks": manifest.metadata.get("semantic_checks", {}),
                "artifact_check": check_result.model_dump(mode="json"),
            }
            report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")
            generated_files.append(
                GeneratedFile(
                    artifact_type=GeneratedArtifactType.DIAGNOSTIC_REPORT,
                    path=relative_artifact_path(report_path, context.output_dir),
                    format=GeneratedArtifactFormat.JSON,
                    checksum=file_sha256(report_path),
                )
            )

        if context.write_manifest:
            manifest = manifest.model_copy(update={"generated_files": generated_files})
            manifest_path = context.output_dir / "artifact_manifest.json"
            manifest_file = GeneratedFile(
                artifact_type=GeneratedArtifactType.MANIFEST,
                path=relative_artifact_path(manifest_path, context.output_dir),
                format=GeneratedArtifactFormat.JSON,
                checksum=None,
            )
            manifest = manifest.model_copy(update={"generated_files": [*generated_files, manifest_file]})
            manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            generated_files.append(manifest_file)

        return GenerationResult(
            status=status,
            backend=self.name,
            capabilities=self.capabilities(),
            manifest=manifest,
            generated_files=generated_files,
            diagnostics=diagnostics,
        )

    def _render_schematic(
        self,
        circuit_ir: CircuitIR,
        layout: SchematicLayout,
        component_views: list[dict[str, Any]],
    ) -> str:
        lines = [
            "(kicad_sch",
            f"  (version {KICAD_FILE_VERSION})",
            '  (generator "schematic_ai")',
            f'  (generator_version "{EDA_BACKEND_VERSION}")',
            f'  (uuid "{self._uuid_text("sheet", circuit_ir.circuit_id, str(circuit_ir.revision))}")',
            '  (paper "A4")',
            "  (title_block",
            f'    (title "{_sexpr_escape(circuit_ir.circuit_id)} derived schematic")',
            f'    (rev "{circuit_ir.revision}")',
            '    (comment 1 "Derived artifact: CircuitIR remains canonical")',
            '    (comment 2 "Manual KiCad edits do not update CircuitIR in Milestone 8")',
            "  )",
            "  (lib_symbols",
        ]
        for view in component_views:
            if view["symbol_resolution"].requires_placeholder:
                lines.extend(self._render_placeholder_lib_symbol(view["component"], view["pin_numbers_by_pin_id"]))
            elif view["symbol_definition"] is not None:
                lines.append(view["symbol_definition"].embedded_text)
        lines.append("  )")

        for view in component_views:
            lines.extend(self._render_symbol_instance(view))

        endpoints_by_pin = {
            endpoint.circuit_pin_id: endpoint
            for view in component_views
            for endpoint in view["pin_endpoints"]
        }
        for net in sorted(circuit_ir.nets, key=lambda item: item.net_id):
            label = self._net_presentation_name(net.net_id, net.name)
            for connection in net.connections:
                endpoint = endpoints_by_pin[connection.pin_id]
                point = endpoint.connection_point
                lines.extend(
                    [
                        f'  (global_label "{_sexpr_escape(label)}"',
                        "    (shape input)",
                        f"    (at {_coord(point['x'])} {_coord(point['y'])} 0)",
                        f'    (uuid "{self._uuid_text("label", net.net_id, connection.component_instance_id, connection.pin_id)}")',
                        '    (effects (font (size 1.27 1.27)) (justify left))',
                        "  )",
                    ]
                )
            note_placement = layout.net_label_placements[net.net_id]
            lines.extend(
                [
                    f'  (text "{_sexpr_escape(self._net_note(circuit_ir, net.net_id))}"',
                    f"    (at {_coord(note_placement.at.x + 20.0)} {_coord(note_placement.at.y)} 0)",
                    f'    (uuid "{self._uuid_text("net-note", net.net_id)}")',
                    '    (effects (font (size 1.0 1.0)) (justify left))',
                    "  )",
                ]
            )

        for component in circuit_ir.components:
            for pin in component.pins:
                if pin.connection_state == PinConnectionState.NO_CONNECT:
                    endpoint = endpoints_by_pin[pin.pin_id]
                    point = endpoint.connection_point
                    lines.extend(
                        [
                            f"  (no_connect (at {_coord(point['x'])} {_coord(point['y'])})",
                            f'    (uuid "{self._uuid_text("no-connect", pin.pin_id)}")',
                            "  )",
                        ]
                    )

        lines.extend(
            [
                "  (symbol_instances",
            ]
        )
        for view in component_views:
            component = view["component"]
            symbol_resolution = view["symbol_resolution"]
            value = self._component_value(component, symbol_resolution)
            footprint = view["footprint_resolution"].footprint_reference
            lines.extend(
                [
                    f'    (path "/{view["backend_object_id"]}"',
                    f'      (reference "{_sexpr_escape(self._reference_designator(component))}")',
                    "      (unit 1)",
                    f'      (value "{_sexpr_escape(value)}")',
                ]
            )
            if footprint is not None:
                lines.append(f'      (footprint "{_sexpr_escape(footprint.library)}:{_sexpr_escape(footprint.footprint_name)}")')
            lines.append("    )")
        lines.extend(
            [
                "  )",
                "  (sheet_instances",
                "    (path \"/\"",
                '      (page "1")',
                "    )",
                "  )",
                ")",
            ]
        )
        return "\n".join(lines) + "\n"

    def _render_placeholder_lib_symbol(self, component: ComponentInstance, pin_numbers_by_pin_id: dict[str, str]) -> list[str]:
        symbol_name = self._placeholder_symbol_name(component.instance_id)
        lines = [
            f'    (symbol "{_sexpr_escape(symbol_name)}"',
            "      (exclude_from_sim no)",
            "      (in_bom yes)",
            "      (on_board yes)",
            '      (property "Reference" "U" (at 0 7.62 0) (effects (font (size 1.27 1.27))))',
            '      (property "Value" "UNRESOLVED PLACEHOLDER" (at 0 -7.62 0) (effects (font (size 1.27 1.27))))',
            f'      (symbol "{_sexpr_escape(symbol_name)}_0_1"',
            "        (rectangle (start -7.62 7.62) (end 7.62 -7.62) (stroke (width 0.254) (type default)) (fill (type none)))",
        ]
        for index, pin in enumerate(component.pins):
            y = 5.08 - index * 2.54
            label = pin_numbers_by_pin_id[pin.pin_id]
            lines.extend(
                [
                    f'        (pin passive line (at -10.16 {_coord(y)} 0) (length 2.54)',
                    f'          (name "{_sexpr_escape(label)}" (effects (font (size 1.0 1.0))))',
                    f'          (number "{_sexpr_escape(label)}" (effects (font (size 1.0 1.0))))',
                    "        )",
                ]
            )
        lines.extend(["      )", "    )"])
        return lines

    def _render_symbol_instance(self, view: dict[str, Any]) -> list[str]:
        component: ComponentInstance = view["component"]
        symbol_resolution: SymbolResolution = view["symbol_resolution"]
        placement: ComponentPlacement = view["placement"]
        footprint = view["footprint_resolution"].footprint_reference
        refdes = self._reference_designator(component)
        value = self._component_value(component, symbol_resolution)
        lib_id = self._placed_lib_id(component, symbol_resolution)

        footprint_text = f"{footprint.library}:{footprint.footprint_name}" if footprint is not None else ""
        lines = [
            "  (symbol",
            f'    (lib_id "{_sexpr_escape(lib_id)}")',
            f"    (at {_coord(placement.at.x)} {_coord(placement.at.y)} 0)",
            "    (unit 1)",
            "    (exclude_from_sim no)",
            "    (in_bom yes)",
            "    (on_board yes)",
            "    (dnp no)",
            f'    (uuid "{view["backend_object_id"]}")',
            f'    (property "Reference" "{_sexpr_escape(refdes)}" (at {_coord(placement.at.x)} {_coord(placement.at.y - 8.0)} 0) (effects (font (size 1.27 1.27))))',
            f'    (property "Value" "{_sexpr_escape(value)}" (at {_coord(placement.at.x)} {_coord(placement.at.y + 8.0)} 0) (effects (font (size 1.27 1.27))))',
            f'    (property "Footprint" "{_sexpr_escape(footprint_text)}" (at {_coord(placement.at.x)} {_coord(placement.at.y + 10.0)} 0) (effects (font (size 1.0 1.0)) hide))',
            f'    (property "CircuitIR_ID" "{_sexpr_escape(component.instance_id)}" (at {_coord(placement.at.x)} {_coord(placement.at.y + 12.0)} 0) (effects (font (size 1.0 1.0)) hide))',
            f'    (property "SchematicAI_Status" "{_sexpr_escape("PLACEHOLDER" if symbol_resolution.requires_placeholder else "RESOLVED_SYMBOL")}" (at {_coord(placement.at.x)} {_coord(placement.at.y + 14.0)} 0) (effects (font (size 1.0 1.0)) hide))',
        ]
        for pin_id, pin_number in view["pin_numbers_by_pin_id"].items():
            lines.append(f'    (pin "{_sexpr_escape(pin_number)}" (uuid "{self._uuid_text("symbol-pin", component.instance_id, pin_id)}"))')
        lines.append("  )")
        for index, pin in enumerate(component.pins):
            net_name = self._net_name_for_pin(component.instance_id, pin.pin_id, view)
            annotation = net_name if pin.connection_state == PinConnectionState.CONNECTED else pin.connection_state.value.upper()
            lines.extend(
                [
                    f'  (text "{_sexpr_escape(self._pin_label(component, pin.pin_id, annotation))}"',
                    f"    (at {_coord(placement.at.x + 13.0)} {_coord(placement.at.y - 7.5 + index * 3.0)} 0)",
                    f'    (uuid "{self._uuid_text("pin-note", pin.pin_id)}")',
                    '    (effects (font (size 0.9 0.9)) (justify left))',
                    "  )",
                ]
            )
        return lines

    def _placed_lib_id(self, component: ComponentInstance, symbol_resolution: SymbolResolution) -> str:
        if symbol_resolution.requires_placeholder:
            return self._placeholder_symbol_name(component.instance_id)
        symbol = symbol_resolution.symbol_reference
        if symbol is None:
            return self._placeholder_symbol_name(component.instance_id)
        return f"{symbol.library}:{symbol.symbol_name}"

    def _pin_endpoints(
        self,
        *,
        component: ComponentInstance,
        symbol_resolution: SymbolResolution,
        pin_numbers_by_pin_id: dict[str, str],
        placement: ComponentPlacement,
        symbol_uuid: str,
        symbol_definition: KiCadSymbolDefinition | None,
    ) -> list[GeneratedPinEndpoint]:
        symbol_pin_points = (
            self._placeholder_pin_points(component, pin_numbers_by_pin_id)
            if symbol_resolution.requires_placeholder
            else symbol_definition.pin_points if symbol_definition is not None else {}
        )
        endpoints = []
        for pin in component.pins:
            pin_number = pin_numbers_by_pin_id.get(pin.pin_id)
            if pin_number is None:
                continue
            relative_point = symbol_pin_points.get(pin_number)
            if relative_point is None:
                continue
            connection_x, connection_y = transform_point(relative_point, (placement.at.x, placement.at.y), 0)
            endpoints.append(
                GeneratedPinEndpoint(
                    circuit_instance_id=component.instance_id,
                    circuit_pin_id=pin.pin_id,
                    symbol_uuid=symbol_uuid,
                    kicad_pin_number=pin_number,
                    position={"x": placement.at.x, "y": placement.at.y},
                    orientation=0,
                    connection_point={"x": connection_x, "y": connection_y},
                )
            )
        return endpoints

    def _placeholder_pin_points(
        self,
        component: ComponentInstance,
        pin_numbers_by_pin_id: dict[str, str],
    ) -> dict[str, tuple[float, float]]:
        points = {}
        for index, pin in enumerate(component.pins):
            label = pin_numbers_by_pin_id[pin.pin_id]
            points[label] = (-10.16, 5.08 - index * 2.54)
        return points

    def _semantic_metadata(self, circuit_ir: CircuitIR, layout: SchematicLayout) -> dict[str, Any]:
        components = {component.instance_id: component for component in circuit_ir.components}
        pins = {pin.pin_id: pin for component in circuit_ir.components for pin in component.pins}
        connectivity = {}
        for net in circuit_ir.nets:
            connectivity[net.net_id] = [
                {
                    "component_instance_id": connection.component_instance_id,
                    "pin_id": connection.pin_id,
                    "reference_designator": components[connection.component_instance_id].reference_designator,
                    "pin_name": pins[connection.pin_id].pin_name,
                    "pin_number": pins[connection.pin_id].pin_number,
                }
                for connection in net.connections
            ]
        no_connects = [
            {"component_instance_id": component.instance_id, "pin_id": pin.pin_id}
            for component in circuit_ir.components
            for pin in component.pins
            if pin.connection_state == PinConnectionState.NO_CONNECT
        ]
        unresolved_pins = [
            {"component_instance_id": component.instance_id, "pin_id": pin.pin_id}
            for component in circuit_ir.components
            for pin in component.pins
            if pin.connection_state == PinConnectionState.UNRESOLVED
        ]
        placements = {
            instance_id: {"x": placement.at.x, "y": placement.at.y, "group_id": placement.group_id}
            for instance_id, placement in sorted(layout.component_placements.items())
        }
        return {
            "target_version": KICAD_TARGET_VERSION,
            "round_trip": False,
            "connectivity": connectivity,
            "no_connects": no_connects,
            "unresolved_pins": unresolved_pins,
            "layout": placements,
            "semantic_checks": {
                "component_count": len(circuit_ir.components),
                "net_count": len(circuit_ir.nets),
                "net_connection_count": sum(len(net.connections) for net in circuit_ir.nets),
            },
        }

    def _manifest(
        self,
        circuit_ir: CircuitIR,
        status: GenerationStatus,
        generated_files: list[GeneratedFile],
        mappings: list[ObjectMapping],
        placeholders: list[PlaceholderRecord],
        unresolved: list[str],
        warnings: list[GenerationDiagnostic],
        errors: list[GenerationDiagnostic],
        metadata: dict[str, Any],
    ) -> GeneratedArtifactManifest:
        return GeneratedArtifactManifest(
            manifest_id=f"MANIFEST_{circuit_ir.circuit_id}_REV_{circuit_ir.revision}_{self.name.upper()}",
            source_circuit_id=circuit_ir.circuit_id,
            source_circuit_revision=circuit_ir.revision,
            backend=self.name,
            backend_version=EDA_BACKEND_VERSION,
            generated_files=generated_files,
            object_mappings=mappings,
            placeholders=placeholders,
            unresolved_objects=unresolved,
            warnings=warnings,
            errors=errors,
            generation_status=status,
            metadata=metadata,
        )

    def _placeholder_record(
        self,
        component: ComponentInstance,
        pin_numbers_by_pin_id: dict[str, str],
        symbol_resolution: SymbolResolution,
    ) -> PlaceholderRecord:
        return PlaceholderRecord(
            placeholder_object_id=f"PLACEHOLDER_{component.instance_id}",
            source_instance_id=component.instance_id,
            backend_object_id=self._component_uuid(component.instance_id),
            reference_designator=self._reference_designator(component),
            display_value=self._component_value(component, symbol_resolution),
            unresolved_reason=symbol_resolution.reason or "component requires placeholder",
            pin_ids=list(pin_numbers_by_pin_id.keys()),
            metadata={"pin_labels": pin_numbers_by_pin_id},
        )

    def _diagnostic(
        self,
        diagnostic_id: str,
        severity: GenerationDiagnosticSeverity,
        category: GenerationDiagnosticCategory,
        message: str,
        source_object_id: str | None = None,
    ) -> GenerationDiagnostic:
        return GenerationDiagnostic(
            diagnostic_id=diagnostic_id,
            severity=severity,
            category=category,
            message=message,
            source_object_id=source_object_id,
        )

    def _component_uuid(self, instance_id: str) -> str:
        return self._uuid_text("component", instance_id)

    def _uuid_text(self, *parts: str) -> str:
        return str(uuid.uuid5(KICAD_NAMESPACE, "::".join(parts)))

    def _reference_designator(self, component: ComponentInstance) -> str:
        if component.reference_designator:
            return component.reference_designator
        prefix = _refdes_prefix(component)
        return f"{prefix}?"

    def _component_value(self, component: ComponentInstance, symbol_resolution: SymbolResolution) -> str:
        if component.value is not None:
            return _format_circuit_value(component.value)
        if symbol_resolution.requires_placeholder:
            role = component.role.replace("_", " ") if component.role else str(component.component_class).replace("_", " ")
            return f"UNRESOLVED PLACEHOLDER: {role}"
        return component.role.replace("_", " ") if component.role else str(component.component_class)

    def _placeholder_symbol_name(self, instance_id: str) -> str:
        return f"SchematicAI:PLACEHOLDER_{instance_id}"

    def _net_presentation_name(self, net_id: str, name: str | None) -> str:
        return net_id

    def _net_note(self, circuit_ir: CircuitIR, net_id: str) -> str:
        components = {component.instance_id: component for component in circuit_ir.components}
        pins = {pin.pin_id: pin for component in circuit_ir.components for pin in component.pins}
        net = next(item for item in circuit_ir.nets if item.net_id == net_id)
        endpoints = []
        for connection in net.connections:
            component = components[connection.component_instance_id]
            pin = pins[connection.pin_id]
            endpoints.append(f"{self._reference_designator(component)}.{pin.pin_name or pin.pin_number or pin.pin_id}")
        endpoint_text = ", ".join(endpoints) if endpoints else "no CircuitIR connections"
        return f"{self._net_presentation_name(net.net_id, net.name)} [{net.net_id}]: {endpoint_text}"

    def _net_name_for_pin(self, component_id: str, pin_id: str, view: dict[str, Any]) -> str:
        circuit_ir = view.get("circuit_ir")
        if circuit_ir is None:
            return "CONNECTED"
        for net in circuit_ir.nets:
            if any(connection.component_instance_id == component_id and connection.pin_id == pin_id for connection in net.connections):
                return self._net_presentation_name(net.net_id, net.name)
        return "CONNECTED"

    def _pin_label(self, component: ComponentInstance, pin_id: str, annotation: str) -> str:
        pin = next(item for item in component.pins if item.pin_id == pin_id)
        label = pin.pin_name or pin.pin_number or pin.pin_id
        return f"{self._reference_designator(component)}.{label}: {annotation}"


def _format_circuit_value(value: CircuitValue) -> str:
    if value.kind == "quantity":
        quantity = value.quantity
        number = int(quantity.value) if float(quantity.value).is_integer() else quantity.value
        return f"{number} {quantity.unit}"
    if value.kind == "text":
        return value.value
    if value.kind == "boolean":
        return "true" if value.value else "false"
    return value.value


def _refdes_prefix(component: ComponentInstance) -> str:
    prefixes = {
        "resistor": "R",
        "capacitor": "C",
        "inductor": "L",
        "diode": "D",
        "mosfet": "Q",
        "transistor": "Q",
        "regulator": "U",
        "converter": "U",
        "sensor": "U",
        "microcontroller": "U",
        "logic": "U",
        "connector": "J",
        "relay": "K",
        "op_amp": "U",
        "isolator": "U",
        "protection_device": "D",
        "interface_ic": "U",
    }
    return prefixes.get(str(component.component_class), "U")


def _sexpr_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _coord(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")
