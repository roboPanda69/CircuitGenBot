"""Generated KiCad artifact parser and translation-fidelity checker."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from schematic_ai.application.eda.models import (
    ArtifactCheckResult,
    GeneratedArtifactManifest,
    GenerationDiagnostic,
    GenerationDiagnosticCategory,
    GenerationDiagnosticSeverity,
)
from schematic_ai.domain.circuit_ir import CircuitIR, PinConnectionState


SExpr = str | list["SExpr"]
SUPPORTED_KICAD_SCHEMATIC_VERSIONS = {"20250114"}


@dataclass(frozen=True)
class ParsedPinEndpoint:
    circuit_instance_id: str
    circuit_pin_id: str
    symbol_uuid: str
    kicad_pin_number: str
    x: float
    y: float

    @property
    def key(self) -> str:
        return f"{self.circuit_instance_id}:{self.circuit_pin_id}"

    @property
    def point(self) -> tuple[float, float]:
        return (_round_coord(self.x), _round_coord(self.y))


@dataclass(frozen=True)
class ParsedSymbol:
    lib_id: str
    uuid: str
    at: tuple[float, float]
    orientation: float
    unit: str | None
    properties: dict[str, str]
    pin_instances: list["ParsedPinInstance"]


@dataclass(frozen=True)
class ParsedPinInstance:
    number: str | None
    uuid: str | None


@dataclass(frozen=True)
class MalformedPlacedSymbol:
    raw_index: int
    symbol_uuid: str | None
    circuit_instance_id: str | None
    errors: tuple[str, ...]


@dataclass(frozen=True)
class PlacedSymbolParseResult:
    parsed_symbols: list[ParsedSymbol]
    malformed_symbols: list[MalformedPlacedSymbol]
    errors: list[str]
    raw_count: int
    parsed_count: int

    @property
    def malformed_count(self) -> int:
        return len(self.malformed_symbols)


@dataclass(frozen=True)
class ParsedSymbolPath:
    path: str
    symbol_uuid: str | None
    reference: str | None
    value: str | None
    unit: str | None
    footprint: str | None
    unsupported_fields: tuple[str, ...]
    duplicate_fields: tuple[str, ...]


@dataclass
class KiCadElectricalGraph:
    nodes: set[tuple[float, float]] = field(default_factory=set)
    wire_edges: list[tuple[tuple[float, float], tuple[float, float]]] = field(default_factory=list)
    pin_endpoints: dict[str, tuple[float, float]] = field(default_factory=dict)
    junctions: set[tuple[float, float]] = field(default_factory=set)
    labels: dict[tuple[float, float], list[str]] = field(default_factory=dict)
    no_connects: set[tuple[float, float]] = field(default_factory=set)


class DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[tuple[float, float], tuple[float, float]] = {}

    def add(self, item: tuple[float, float]) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: tuple[float, float]) -> tuple[float, float]:
        self.add(item)
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: tuple[float, float], right: tuple[float, float]) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


class KiCadArtifactChecker:
    """Validate generated schematic fidelity without importing KiCad into CircuitIR."""

    def check(
        self,
        *,
        schematic_path: str | Path,
        circuit_ir: CircuitIR,
        manifest: GeneratedArtifactManifest,
    ) -> ArtifactCheckResult:
        parse_errors: list[str] = []
        try:
            root = parse_sexpr(Path(schematic_path).read_text(encoding="utf-8"))
        except ValueError as exc:
            return ArtifactCheckResult(valid=False, parse_errors=[str(exc)])

        if not isinstance(root, list) or atom(root, 0) != "kicad_sch":
            return ArtifactCheckResult(valid=False, parse_errors=["root expression is not kicad_sch"])

        lib_pins = self._lib_symbol_pins(root)
        symbol_parse_result = self._symbol_instances(root)
        symbols = symbol_parse_result.parsed_symbols
        symbol_paths = self._symbol_paths(root)
        endpoint_records = self._endpoint_records(root)
        manifest_pin_numbers = self._manifest_pin_numbers(manifest)
        structural_errors = self._structural_errors(
            root,
            circuit_ir=circuit_ir,
            manifest=manifest,
            lib_pins=lib_pins,
            symbol_parse_result=symbol_parse_result,
            symbol_paths=symbol_paths,
            manifest_pin_numbers=manifest_pin_numbers,
        )
        if structural_errors:
            return ArtifactCheckResult(
                valid=False,
                parse_errors=structural_errors,
                diagnostics=[_artifact_check_failed_diagnostic()],
                expected_connectivity=_expected_connectivity(circuit_ir),
                expected_no_connects=_expected_no_connects(circuit_ir),
            )

        component_mismatches: list[str] = []
        refdes_mismatches: list[str] = []
        value_mismatches: list[str] = []
        placeholder_mismatches: list[str] = []
        endpoint_mismatches: list[str] = []

        symbol_by_component: dict[str, ParsedSymbol] = {}
        for symbol in symbols:
            circuit_id = symbol.properties.get("CircuitIR_ID")
            if circuit_id:
                symbol_by_component[circuit_id] = symbol

        placeholder_ids = {placeholder.source_instance_id for placeholder in manifest.placeholders}
        for component in circuit_ir.components:
            symbol = symbol_by_component.get(component.instance_id)
            if symbol is None:
                component_mismatches.append(f"missing symbol for {component.instance_id}")
                continue
            if symbol.properties.get("Reference") != component.reference_designator:
                refdes_mismatches.append(f"{component.instance_id} refdes mismatch")
            expected_value = _expected_component_value(component, component.instance_id in placeholder_ids)
            if symbol.properties.get("Value") != expected_value:
                value_mismatches.append(f"{component.instance_id} value mismatch")

        for placeholder_id in placeholder_ids:
            symbol = symbol_by_component.get(placeholder_id)
            if symbol is None:
                placeholder_mismatches.append(f"placeholder symbol missing for {placeholder_id}")
            elif symbol.properties.get("SchematicAI_Status") != "PLACEHOLDER":
                placeholder_mismatches.append(f"placeholder {placeholder_id} is not an editable placeholder symbol instance")

        endpoints: dict[str, ParsedPinEndpoint] = {}
        for component in circuit_ir.components:
            symbol = symbol_by_component.get(component.instance_id)
            if symbol is None:
                continue
            symbol_pins = lib_pins.get(symbol.lib_id)
            if symbol_pins is None:
                endpoint_mismatches.append(f"missing embedded symbol definition for {component.instance_id} lib_id {symbol.lib_id}")
                continue
            for pin in component.pins:
                kicad_pin_number = manifest_pin_numbers.get(component.instance_id, {}).get(pin.pin_id)
                if kicad_pin_number is None:
                    if pin.connection_state != PinConnectionState.UNRESOLVED:
                        endpoint_mismatches.append(f"missing generated pin mapping for {pin.pin_id}")
                    continue
                relative = symbol_pins.get(kicad_pin_number)
                if relative is None:
                    endpoint_mismatches.append(f"symbol {component.instance_id} lacks pin {kicad_pin_number}")
                    continue
                point = transform_point(relative, symbol.at, symbol.orientation)
                endpoints[pin.pin_id] = ParsedPinEndpoint(
                    circuit_instance_id=component.instance_id,
                    circuit_pin_id=pin.pin_id,
                    symbol_uuid=symbol.uuid,
                    kicad_pin_number=kicad_pin_number,
                    x=point[0],
                    y=point[1],
                )

        for endpoint_record in endpoint_records:
            endpoint = endpoints.get(endpoint_record.circuit_pin_id)
            if endpoint is None:
                endpoint_mismatches.append(f"endpoint record has no parsed pin endpoint for {endpoint_record.circuit_pin_id}")
            elif endpoint.point != endpoint_record.point:
                endpoint_mismatches.append(f"endpoint record point mismatch for {endpoint_record.circuit_pin_id}")

        graph = self._electrical_graph(root, endpoints)
        connected_components = self._connected_components(graph)
        point_to_component = {
            point: component_root
            for component_root, points in connected_components.items()
            for point in points
        }
        component_labels = self._component_labels(graph, point_to_component)
        label_to_net = self._label_to_net(manifest)

        expected = _expected_connectivity(circuit_ir)
        generated = {net_id: [] for net_id in expected}
        net_mismatches = list(endpoint_mismatches)
        for component_root, labels in component_labels.items():
            canonical_net_ids = sorted({label_to_net[label] for label in labels if label in label_to_net})
            if len(canonical_net_ids) > 1:
                net_mismatches.append(f"electrical component {component_root} has conflicting canonical labels {canonical_net_ids}")

        for pin in (pin for component in circuit_ir.components for pin in component.pins if pin.connection_state == PinConnectionState.CONNECTED):
            endpoint = endpoints.get(pin.pin_id)
            if endpoint is None:
                continue
            component_root = point_to_component.get(endpoint.point)
            if component_root is None:
                continue
            labels = component_labels.get(component_root, [])
            canonical_net_ids = sorted({label_to_net[label] for label in labels if label in label_to_net})
            if len(canonical_net_ids) == 1:
                generated.setdefault(canonical_net_ids[0], []).append(endpoint.key)
        generated = {net_id: sorted(set(keys)) for net_id, keys in generated.items()}

        for net_id, expected_keys in expected.items():
            if generated.get(net_id, []) != expected_keys:
                net_mismatches.append(f"{net_id} expected {expected_keys} generated {generated.get(net_id, [])}")

        expected_no_connects = _expected_no_connects(circuit_ir)
        generated_no_connects: list[str] = []
        accidental_no_connects: list[str] = []
        no_connect_mismatches: list[str] = []
        for pin in (pin for component in circuit_ir.components for pin in component.pins):
            endpoint = endpoints.get(pin.pin_id)
            if endpoint is None:
                continue
            if endpoint.point in graph.no_connects:
                key = endpoint.key
                if pin.connection_state == PinConnectionState.NO_CONNECT:
                    generated_no_connects.append(key)
                else:
                    accidental_no_connects.append(key)
        generated_no_connects = sorted(generated_no_connects)
        if generated_no_connects != expected_no_connects:
            no_connect_mismatches.append(f"expected no-connects {expected_no_connects} generated {generated_no_connects}")
        if accidental_no_connects:
            no_connect_mismatches.append(f"accidental no-connect markers on {sorted(accidental_no_connects)}")
        for component in circuit_ir.components:
            for pin in component.pins:
                if pin.connection_state != PinConnectionState.NO_CONNECT:
                    continue
                endpoint = endpoints.get(pin.pin_id)
                if endpoint is None:
                    continue
                component_root = point_to_component.get(endpoint.point)
                if component_root is not None and component_labels.get(component_root):
                    no_connect_mismatches.append(f"no-connect pin {endpoint.key} is also label-connected")
                if any(endpoint.point in edge for edge in graph.wire_edges):
                    no_connect_mismatches.append(f"no-connect pin {endpoint.key} is wired")

        all_parse_errors = [*parse_errors, *structural_errors]
        valid = not (
            all_parse_errors
            or component_mismatches
            or net_mismatches
            or no_connect_mismatches
            or refdes_mismatches
            or value_mismatches
            or placeholder_mismatches
        )
        diagnostics = []
        if not valid:
            diagnostics.append(_artifact_check_failed_diagnostic())

        return ArtifactCheckResult(
            valid=valid,
            component_mismatches=component_mismatches,
            net_mismatches=net_mismatches,
            no_connect_mismatches=no_connect_mismatches,
            refdes_mismatches=refdes_mismatches,
            value_mismatches=value_mismatches,
            placeholder_mismatches=placeholder_mismatches,
            parse_errors=all_parse_errors,
            diagnostics=diagnostics,
            generated_connectivity=generated,
            expected_connectivity=expected,
            generated_no_connects=generated_no_connects,
            expected_no_connects=expected_no_connects,
        )

    def _structural_errors(
        self,
        root: list[SExpr],
        *,
        circuit_ir: CircuitIR,
        manifest: GeneratedArtifactManifest,
        lib_pins: dict[str, dict[str, tuple[float, float]]],
        symbol_parse_result: PlacedSymbolParseResult,
        symbol_paths: list[ParsedSymbolPath],
        manifest_pin_numbers: dict[str, dict[str, str]],
    ) -> list[str]:
        errors = list(symbol_parse_result.errors)
        symbols = symbol_parse_result.parsed_symbols
        if symbol_parse_result.raw_count != symbol_parse_result.parsed_count + symbol_parse_result.malformed_count:
            errors.append(
                "placed symbol accounting invariant failed: "
                f"raw={symbol_parse_result.raw_count} parsed={symbol_parse_result.parsed_count} "
                f"malformed={symbol_parse_result.malformed_count}"
            )
        if symbol_parse_result.malformed_count:
            errors.append(
                "malformed_placed_symbol_count: "
                f"raw={symbol_parse_result.raw_count} parsed={symbol_parse_result.parsed_count} "
                f"malformed={symbol_parse_result.malformed_count}"
            )
        version = value_of_child(root, "version")
        if version not in SUPPORTED_KICAD_SCHEMATIC_VERSIONS:
            errors.append(f"unsupported KiCad schematic version {version!r}")
        if value_of_child(root, "generator") != "schematic_ai":
            errors.append("missing expected schematic_ai generator field")
        if first_child(root, "lib_symbols") is None:
            errors.append("missing required lib_symbols section")
        symbol_instances = first_child(root, "symbol_instances")
        if symbol_instances is None:
            errors.append("missing required symbol_instances section")
        sheet_instances = first_child(root, "sheet_instances")
        if sheet_instances is None or first_child(sheet_instances, "path") is None:
            errors.append("missing required sheet_instances root path")
        uuid_values: list[str] = []
        for node in _walk(root):
            if isinstance(node, list) and atom(node, 0) == "uuid":
                uuid_values.append(atom(node, 1) or "")
                try:
                    UUID(atom(node, 1) or "")
                except ValueError:
                    errors.append(f"malformed UUID {atom(node, 1)!r}")
        for duplicate_uuid in sorted(_duplicates(uuid_values)):
            errors.append(f"duplicate UUID {duplicate_uuid}")
        lib_symbols = first_child(root, "lib_symbols")
        lib_ids = {atom(symbol, 1) for symbol in children(lib_symbols, "symbol")} if lib_symbols is not None else set()
        symbol_uuids = [symbol.uuid for symbol in symbols]
        for duplicate_symbol_uuid in sorted(_duplicates(symbol_uuids)):
            errors.append(f"duplicate placed symbol UUID {duplicate_symbol_uuid}")

        expected_component_ids = {
            mapping.source_object_id
            for mapping in manifest.object_mappings
            if mapping.source_object_type == "component_instance"
        }
        component_by_id = {component.instance_id: component for component in circuit_ir.components}
        component_mappings = {
            mapping.source_object_id: mapping
            for mapping in manifest.object_mappings
            if mapping.source_object_type == "component_instance"
        }
        placeholder_ids = {placeholder.source_instance_id for placeholder in manifest.placeholders}
        symbols_by_component: dict[str, list[ParsedSymbol]] = {}
        symbols_by_uuid: dict[str, list[ParsedSymbol]] = {}
        for symbol in symbols:
            symbols_by_uuid.setdefault(symbol.uuid, []).append(symbol)
            circuit_id = symbol.properties.get("CircuitIR_ID")
            if circuit_id is None:
                errors.append(f"unexpected placed symbol {symbol.uuid} missing CircuitIR_ID")
                continue
            symbols_by_component.setdefault(circuit_id, []).append(symbol)
            if circuit_id not in expected_component_ids:
                errors.append(f"unexpected placed symbol {symbol.uuid} for {circuit_id}")
        for component_id in sorted(expected_component_ids):
            count = len(symbols_by_component.get(component_id, []))
            if count == 0:
                errors.append(f"missing placed symbol for represented component {component_id}")
            elif count > 1:
                errors.append(f"duplicate placed symbols for represented component {component_id}")

        paths_by_uuid: dict[str, list[ParsedSymbolPath]] = {}
        path_ids = [path.path for path in symbol_paths]
        for duplicate_path in sorted(_duplicates(path_ids)):
            errors.append(f"duplicate symbol_instances path {duplicate_path}")
        for path in symbol_paths:
            if not path.path.startswith("/"):
                errors.append(f"symbol_instances path {path.path!r} missing leading slash")
                continue
            uuid_text = path.path[1:]
            try:
                UUID(uuid_text)
            except ValueError:
                errors.append(f"malformed symbol_instances path UUID {path.path!r}")
                continue
            paths_by_uuid.setdefault(uuid_text, []).append(path)
            if path.symbol_uuid is None or path.symbol_uuid != uuid_text:
                errors.append(f"symbol_instances path {path.path!r} UUID identity mismatch")
            if path.reference is None:
                errors.append(f"symbol_instances path {path.path} missing reference")
            if path.value is None:
                errors.append(f"symbol_instances path {path.path} missing value")
            if path.unit is None:
                errors.append(f"symbol_instances path {path.path} missing unit")
            elif path.unit != "1":
                errors.append(f"symbol_instances path {path.path} unsupported unit {path.unit}")
            for field_name in path.unsupported_fields:
                errors.append(f"symbol_instances path {path.path} has unsupported field {field_name}")
            for field_name in path.duplicate_fields:
                errors.append(f"symbol_instances path {path.path} has duplicate field {field_name}")
        for symbol_uuid in sorted(paths_by_uuid):
            if symbol_uuid not in symbols_by_uuid:
                errors.append(f"orphan symbol_instances path for absent symbol {symbol_uuid}")

        for symbol in symbols:
            lib_id = symbol.lib_id
            symbol_uuid = symbol.uuid
            if lib_id is None:
                errors.append("symbol instance missing lib_id")
            elif lib_id not in lib_ids:
                errors.append(f"symbol instance lib_id {lib_id} has no embedded definition")
            if symbol.at is None:
                errors.append(f"symbol instance {symbol_uuid} missing at")
            if symbol.orientation != 0:
                errors.append(f"symbol instance {symbol_uuid} unsupported orientation {symbol.orientation:g}")
            if symbol.unit is None:
                errors.append(f"symbol instance {symbol_uuid} missing unit")
            elif symbol.unit != "1":
                errors.append(f"symbol instance {symbol_uuid} unsupported unit {symbol.unit}")
            props = symbol.properties
            circuit_id = props.get("CircuitIR_ID")
            component = component_by_id.get(circuit_id or "")
            if circuit_id is not None and component is not None:
                mapping = component_mappings.get(circuit_id)
                expected_uuid = mapping.backend_object_id if mapping is not None else None
                if expected_uuid != symbol_uuid:
                    errors.append(f"symbol UUID for {circuit_id} does not match manifest mapping")
                expected_ref = component.reference_designator
                expected_value = _expected_component_value(component, circuit_id in placeholder_ids)
                expected_lib_id = _expected_lib_id(component, circuit_id in placeholder_ids)
                if expected_lib_id is not None and lib_id != expected_lib_id:
                    errors.append(f"symbol instance {symbol_uuid} lib_id {lib_id} does not match expected {expected_lib_id}")
                manifest_lib_id = mapping.metadata.get("lib_id") if mapping is not None else None
                if not isinstance(manifest_lib_id, str) or not manifest_lib_id:
                    errors.append(f"manifest mapping for {circuit_id} missing lib_id identity")
                elif manifest_lib_id != lib_id:
                    errors.append(f"symbol instance {symbol_uuid} lib_id {lib_id} does not match manifest {manifest_lib_id}")
                if props.get("Reference") != expected_ref:
                    errors.append(f"symbol instance {symbol_uuid} Reference property mismatch")
                if props.get("Value") != expected_value:
                    errors.append(f"symbol instance {symbol_uuid} Value property mismatch")
                if circuit_id in placeholder_ids and props.get("SchematicAI_Status") != "PLACEHOLDER":
                    errors.append(f"placeholder symbol {circuit_id} missing PLACEHOLDER status")
                if circuit_id not in placeholder_ids and props.get("SchematicAI_Status") != "RESOLVED_SYMBOL":
                    errors.append(f"resolved symbol {circuit_id} missing RESOLVED_SYMBOL status")
            if "Reference" not in props:
                errors.append(f"symbol instance {symbol_uuid} missing Reference property")
            if "Value" not in props:
                errors.append(f"symbol instance {symbol_uuid} missing Value property")
            matching_paths = paths_by_uuid.get(symbol_uuid, [])
            if len(matching_paths) == 0:
                errors.append(f"missing symbol_instances path for placed symbol {symbol_uuid}")
            elif len(matching_paths) > 1:
                errors.append(f"duplicate symbol_instances paths for placed symbol {symbol_uuid}")
            else:
                path = matching_paths[0]
                if path.reference != props.get("Reference"):
                    errors.append(f"symbol_instances path reference mismatch for {symbol_uuid}")
                if path.value != props.get("Value"):
                    errors.append(f"symbol_instances path value mismatch for {symbol_uuid}")
                if path.unit != symbol.unit:
                    errors.append(f"symbol_instances path unit mismatch for {symbol_uuid}")
                expected_footprint = props.get("Footprint") or None
                if path.footprint != expected_footprint:
                    errors.append(f"symbol_instances path footprint mismatch for {symbol_uuid}")

            expected_pins = set(lib_pins.get(lib_id, {}))
            if not expected_pins:
                errors.append(f"symbol instance {symbol_uuid} has no supported embedded pin definition")
            actual_pins = [pin.number for pin in symbol.pin_instances if pin.number is not None]
            actual_pin_set = set(actual_pins)
            for duplicate_pin in sorted(_duplicates(actual_pins)):
                errors.append(f"duplicate placed pin number {duplicate_pin} on symbol {symbol_uuid}")
            pin_uuids = [pin.uuid for pin in symbol.pin_instances if pin.uuid is not None]
            for duplicate_pin_uuid in sorted(_duplicates(pin_uuids)):
                errors.append(f"duplicate placed pin UUID {duplicate_pin_uuid} on symbol {symbol_uuid}")
            for pin_instance in symbol.pin_instances:
                if pin_instance.number is None:
                    errors.append(f"placed pin instance on symbol {symbol_uuid} missing pin number")
                elif pin_instance.number not in expected_pins:
                    errors.append(f"extra_symbol_pin_instances: symbol {symbol_uuid} has unexpected pin {pin_instance.number}")
                if pin_instance.uuid is None:
                    errors.append(f"placed pin {pin_instance.number} on symbol {symbol_uuid} missing uuid")
                else:
                    try:
                        UUID(pin_instance.uuid)
                    except ValueError:
                        errors.append(f"malformed placed pin UUID {pin_instance.uuid!r} on symbol {symbol_uuid}")
            missing_pins = sorted(expected_pins - actual_pin_set)
            extra_pins = sorted(actual_pin_set - expected_pins)
            if missing_pins:
                errors.append(f"missing_symbol_pin_instances: symbol {symbol_uuid} missing pins {missing_pins}")
            if extra_pins:
                errors.append(f"extra_symbol_pin_instances: symbol {symbol_uuid} extra pins {extra_pins}")
            if circuit_id is not None:
                expected_mapped_pins = set(manifest_pin_numbers.get(circuit_id, {}).values())
                if expected_mapped_pins and not expected_mapped_pins.issubset(actual_pin_set):
                    errors.append(f"manifest mapped pins for {circuit_id} are absent from placed symbol instance")
        return errors

    def _lib_symbol_pins(self, root: list[SExpr]) -> dict[str, dict[str, tuple[float, float]]]:
        pins_by_symbol: dict[str, dict[str, tuple[float, float]]] = {}
        lib_symbols = first_child(root, "lib_symbols")
        if lib_symbols is None:
            return pins_by_symbol
        for symbol in children(lib_symbols, "symbol"):
            symbol_name = atom(symbol, 1)
            if symbol_name is not None:
                pins_by_symbol[symbol_name] = collect_symbol_pin_points(symbol)
        return pins_by_symbol

    def _symbol_instances(self, root: list[SExpr]) -> PlacedSymbolParseResult:
        raw_symbols = children(root, "symbol")
        parsed: list[ParsedSymbol] = []
        malformed: list[MalformedPlacedSymbol] = []
        parse_errors: list[str] = []
        for raw_index, symbol in enumerate(raw_symbols):
            lib_id = value_of_child(symbol, "lib_id")
            symbol_uuid = value_of_child(symbol, "uuid")
            at_expr = first_child(symbol, "at")
            circuit_instance_id = symbol_properties(symbol).get("CircuitIR_ID")
            symbol_label = symbol_uuid or circuit_instance_id or f"raw-index-{raw_index}"
            symbol_errors: list[str] = []
            if lib_id is None:
                symbol_errors.append(f"missing_symbol_lib_id: placed symbol {symbol_label} missing lib_id")
            if symbol_uuid is None:
                symbol_errors.append(f"missing_symbol_uuid: placed symbol {symbol_label} missing uuid")
            if at_expr is None:
                symbol_errors.append(f"missing_symbol_at: placed symbol {symbol_label} missing at")

            at: tuple[float, float] | None = None
            orientation: float | None = None
            if at_expr is not None:
                x_text = atom(at_expr, 1)
                y_text = atom(at_expr, 2)
                orientation_text = atom(at_expr, 3)
                try:
                    if x_text is None:
                        raise ValueError
                    x = _round_coord(float(x_text))
                except ValueError:
                    symbol_errors.append(f"malformed_symbol_x: placed symbol {symbol_label} has invalid x {x_text!r}")
                try:
                    if y_text is None:
                        raise ValueError
                    y = _round_coord(float(y_text))
                except ValueError:
                    symbol_errors.append(f"malformed_symbol_y: placed symbol {symbol_label} has invalid y {y_text!r}")
                try:
                    if orientation_text is None:
                        raise ValueError
                    orientation = float(orientation_text)
                except ValueError:
                    symbol_errors.append(
                        f"malformed_symbol_orientation: placed symbol {symbol_label} has invalid orientation {orientation_text!r}"
                    )
                if not any(error.startswith(("malformed_symbol_x:", "malformed_symbol_y:")) for error in symbol_errors):
                    at = (x, y)

            if symbol_errors:
                parse_errors.extend(symbol_errors)
                malformed.append(
                    MalformedPlacedSymbol(
                        raw_index=raw_index,
                        symbol_uuid=symbol_uuid,
                        circuit_instance_id=circuit_instance_id,
                        errors=tuple(symbol_errors),
                    )
                )
                continue
            assert lib_id is not None and symbol_uuid is not None and at is not None and orientation is not None
            parsed.append(
                ParsedSymbol(
                    lib_id=lib_id,
                    uuid=symbol_uuid,
                    at=at,
                    orientation=orientation,
                    unit=value_of_child(symbol, "unit"),
                    properties=symbol_properties(symbol),
                    pin_instances=[
                        ParsedPinInstance(number=atom(pin, 1), uuid=value_of_child(pin, "uuid"))
                        for pin in children(symbol, "pin")
                    ],
                )
            )
        return PlacedSymbolParseResult(
            parsed_symbols=parsed,
            malformed_symbols=malformed,
            errors=parse_errors,
            raw_count=len(raw_symbols),
            parsed_count=len(parsed),
        )

    def _symbol_paths(self, root: list[SExpr]) -> list[ParsedSymbolPath]:
        symbol_instances = first_child(root, "symbol_instances")
        paths = []
        for path in children(symbol_instances, "path"):
            path_id = atom(path, 1) or ""
            field_names = [atom(field, 0) or "" for field in path[2:] if isinstance(field, list)]
            supported_fields = {"reference", "unit", "value", "footprint"}
            paths.append(
                ParsedSymbolPath(
                    path=path_id,
                    symbol_uuid=path_id[1:] if path_id.startswith("/") else None,
                    reference=value_of_child(path, "reference"),
                    value=value_of_child(path, "value"),
                    unit=value_of_child(path, "unit"),
                    footprint=value_of_child(path, "footprint"),
                    unsupported_fields=tuple(sorted({name for name in field_names if name not in supported_fields})),
                    duplicate_fields=tuple(sorted(_duplicates(field_names))),
                )
            )
        return paths

    def _endpoint_records(self, root: list[SExpr]) -> list[ParsedPinEndpoint]:
        endpoints = []
        for text in children(root, "text"):
            if atom(text, 1) != "SCHEMATIC_AI_ENDPOINT":
                continue
            props = symbol_properties(text)
            try:
                endpoints.append(
                    ParsedPinEndpoint(
                        circuit_instance_id=props["CircuitIR_Instance"],
                        circuit_pin_id=props["CircuitIR_Pin"],
                        symbol_uuid=props["Symbol_UUID"],
                        kicad_pin_number=props["KiCad_Pin"],
                        x=float(props["Connection_X"]),
                        y=float(props["Connection_Y"]),
                    )
                )
            except (KeyError, ValueError):
                continue
        return endpoints

    def _electrical_graph(self, root: list[SExpr], endpoints: dict[str, ParsedPinEndpoint]) -> KiCadElectricalGraph:
        graph = KiCadElectricalGraph()
        for endpoint in endpoints.values():
            graph.nodes.add(endpoint.point)
            graph.pin_endpoints[endpoint.key] = endpoint.point
        for label in children(root, "global_label"):
            name = atom(label, 1)
            at_expr = first_child(label, "at")
            if name is None or at_expr is None:
                continue
            point = coord_from_at(at_expr)
            graph.nodes.add(point)
            graph.labels.setdefault(point, []).append(name)
        for no_connect in children(root, "no_connect"):
            at_expr = first_child(no_connect, "at")
            if at_expr is None:
                continue
            point = coord_from_at(at_expr)
            graph.nodes.add(point)
            graph.no_connects.add(point)
        for junction in children(root, "junction"):
            at_expr = first_child(junction, "at")
            if at_expr is None:
                continue
            point = coord_from_at(at_expr)
            graph.nodes.add(point)
            graph.junctions.add(point)
        for wire in children(root, "wire"):
            points = wire_points(wire)
            for start, end in zip(points, points[1:]):
                split_points = sorted(
                    {point for point in graph.nodes | {start, end} if point_on_segment(point, start, end)},
                    key=lambda point: ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2),
                )
                graph.nodes.update(split_points)
                for left, right in zip(split_points, split_points[1:]):
                    if left != right:
                        graph.wire_edges.append((left, right))
        return graph

    def _connected_components(self, graph: KiCadElectricalGraph) -> dict[tuple[float, float], set[tuple[float, float]]]:
        dsu = DisjointSet()
        for node in graph.nodes:
            dsu.add(node)
        for start, end in graph.wire_edges:
            dsu.union(start, end)
        labels_by_name: dict[str, list[tuple[float, float]]] = {}
        for point, labels in graph.labels.items():
            for label in labels:
                labels_by_name.setdefault(label, []).append(point)
        for points in labels_by_name.values():
            for point in points[1:]:
                dsu.union(points[0], point)
        components: dict[tuple[float, float], set[tuple[float, float]]] = {}
        for node in graph.nodes:
            components.setdefault(dsu.find(node), set()).add(node)
        return components

    def _component_labels(
        self,
        graph: KiCadElectricalGraph,
        point_to_component: dict[tuple[float, float], tuple[float, float]],
    ) -> dict[tuple[float, float], list[str]]:
        labels: dict[tuple[float, float], list[str]] = {}
        for point, label_names in graph.labels.items():
            component_root = point_to_component.get(point, point)
            labels.setdefault(component_root, []).extend(label_names)
        return labels

    def _label_to_net(self, manifest: GeneratedArtifactManifest) -> dict[str, str]:
        mapping = {}
        for object_mapping in manifest.object_mappings:
            if object_mapping.source_object_type == "net":
                label = object_mapping.metadata.get("net_label")
                if label:
                    mapping[label] = object_mapping.source_object_id
        return mapping

    def _manifest_pin_numbers(self, manifest: GeneratedArtifactManifest) -> dict[str, dict[str, str]]:
        mapping: dict[str, dict[str, str]] = {}
        for object_mapping in manifest.object_mappings:
            if object_mapping.source_object_type != "component_instance":
                continue
            pin_numbers = {}
            for endpoint in object_mapping.metadata.get("pin_endpoints", []):
                circuit_pin_id = endpoint.get("circuit_pin_id")
                kicad_pin_number = endpoint.get("kicad_pin_number")
                if circuit_pin_id and kicad_pin_number:
                    pin_numbers[circuit_pin_id] = kicad_pin_number
            mapping[object_mapping.source_object_id] = pin_numbers
        return mapping


def parse_sexpr(text: str) -> SExpr:
    tokens = tokenize(text)
    stack: list[list[SExpr]] = []
    current: list[SExpr] | None = None
    root: SExpr | None = None
    for token in tokens:
        if token == "(":
            new_expr: list[SExpr] = []
            if current is not None:
                current.append(new_expr)
                stack.append(current)
            current = new_expr
        elif token == ")":
            if current is None:
                raise ValueError("unexpected closing parenthesis")
            root = current
            current = stack.pop() if stack else None
        else:
            if current is None:
                raise ValueError("atom outside expression")
            current.append(token)
    if current is not None or stack:
        raise ValueError("unclosed S-expression")
    if root is None:
        raise ValueError("empty S-expression")
    return root


def tokenize(text: str) -> list[str]:
    tokens = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif char in "()":
            tokens.append(char)
            index += 1
        elif char == '"':
            index += 1
            value = []
            while index < len(text):
                char = text[index]
                if char == "\\" and index + 1 < len(text):
                    value.append(text[index + 1])
                    index += 2
                    continue
                if char == '"':
                    index += 1
                    break
                value.append(char)
                index += 1
            else:
                raise ValueError("unterminated quoted string")
            tokens.append("".join(value))
        else:
            start = index
            while index < len(text) and not text[index].isspace() and text[index] not in "()":
                index += 1
            tokens.append(text[start:index])
    return tokens


def children(expr: list[SExpr] | None, name: str) -> list[list[SExpr]]:
    if expr is None:
        return []
    return [child for child in expr if isinstance(child, list) and atom(child, 0) == name]


def first_child(expr: list[SExpr] | None, name: str) -> list[SExpr] | None:
    return next((child for child in children(expr, name)), None)


def atom(expr: list[SExpr], index: int) -> str | None:
    if index >= len(expr):
        return None
    value = expr[index]
    return value if isinstance(value, str) else None


def value_of_child(expr: list[SExpr], name: str) -> str | None:
    child = first_child(expr, name)
    return atom(child, 1) if child is not None else None


def symbol_properties(expr: list[SExpr]) -> dict[str, str]:
    values = {}
    for prop in children(expr, "property"):
        key = atom(prop, 1)
        value = atom(prop, 2)
        if key is not None and value is not None:
            values[key] = value
    return values


def collect_symbol_pin_points(expr: list[SExpr]) -> dict[str, tuple[float, float]]:
    style_symbols = children(expr, "symbol")
    if len(style_symbols) != 1 or not ((atom(style_symbols[0], 1) or "").endswith("_0_1")):
        return {}
    pins = {}
    for node in children(style_symbols[0], "pin"):
        at_expr = first_child(node, "at")
        number_expr = first_child(node, "number")
        number = atom(number_expr, 1) if number_expr is not None else None
        if at_expr is not None and number is not None:
            pins[number] = coord_from_at(at_expr)
    return pins


def wire_points(wire: list[SExpr]) -> list[tuple[float, float]]:
    pts = first_child(wire, "pts")
    if pts is None:
        return []
    return [coord_from_xy(xy) for xy in children(pts, "xy")]


def coord_from_xy(expr: list[SExpr]) -> tuple[float, float]:
    return (_round_coord(float(atom(expr, 1) or 0)), _round_coord(float(atom(expr, 2) or 0)))


def coord_from_at(expr: list[SExpr]) -> tuple[float, float]:
    return (_round_coord(float(atom(expr, 1) or 0)), _round_coord(float(atom(expr, 2) or 0)))


def point_on_segment(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> bool:
    px, py = point
    sx, sy = start
    ex, ey = end
    cross = (px - sx) * (ey - sy) - (py - sy) * (ex - sx)
    if abs(cross) > 0.0001:
        return False
    return min(sx, ex) <= px <= max(sx, ex) and min(sy, ey) <= py <= max(sy, ey)


def _walk(expr: SExpr) -> list[SExpr]:
    nodes = [expr]
    if isinstance(expr, list):
        for child in expr:
            nodes.extend(_walk(child))
    return nodes


def transform_point(relative: tuple[float, float], origin: tuple[float, float], orientation: float) -> tuple[float, float]:
    x, y = relative
    normalized = int(orientation) % 360
    if normalized == 0:
        rx, ry = x, y
    elif normalized == 90:
        rx, ry = -y, x
    elif normalized == 180:
        rx, ry = -x, -y
    elif normalized == 270:
        rx, ry = y, -x
    else:
        raise ValueError(f"unsupported symbol orientation {orientation}")
    return (_round_coord(origin[0] + rx), _round_coord(origin[1] + ry))


def _format_check_value(value: Any) -> str:
    if value.kind == "quantity":
        number = int(value.quantity.value) if float(value.quantity.value).is_integer() else value.quantity.value
        return f"{number} {value.quantity.unit}"
    if value.kind == "text":
        return value.value
    if value.kind == "boolean":
        return "true" if value.value else "false"
    return value.value


def _expected_component_value(component: Any, is_placeholder: bool) -> str:
    if component.value is not None:
        return _format_check_value(component.value)
    if is_placeholder:
        role = component.role.replace("_", " ") if component.role else str(component.component_class).replace("_", " ")
        return f"UNRESOLVED PLACEHOLDER: {role}"
    return component.role.replace("_", " ") if component.role else str(component.component_class)


def _expected_connectivity(circuit_ir: CircuitIR) -> dict[str, list[str]]:
    return {
        net.net_id: sorted(f"{connection.component_instance_id}:{connection.pin_id}" for connection in net.connections)
        for net in circuit_ir.nets
    }


def _expected_no_connects(circuit_ir: CircuitIR) -> list[str]:
    return sorted(
        f"{component.instance_id}:{pin.pin_id}"
        for component in circuit_ir.components
        for pin in component.pins
        if pin.connection_state == PinConnectionState.NO_CONNECT
    )


def _expected_lib_id(component: Any, is_placeholder: bool) -> str | None:
    if is_placeholder:
        return f"SchematicAI:PLACEHOLDER_{component.instance_id}"
    symbol_reference = component.symbol_reference
    if symbol_reference is None:
        return None
    return f"{symbol_reference.library}:{symbol_reference.symbol_name}"


def _duplicates(values: list[str]) -> set[str]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _artifact_check_failed_diagnostic() -> GenerationDiagnostic:
    return GenerationDiagnostic(
        diagnostic_id="ARTIFACT_CHECK_FAILED",
        severity=GenerationDiagnosticSeverity.ERROR,
        category=GenerationDiagnosticCategory.ARTIFACT_CHECK_FAILED,
        message="generated KiCad artifact does not match CircuitIR translation graph",
    )


def _round_coord(value: float) -> float:
    return round(value, 3)
