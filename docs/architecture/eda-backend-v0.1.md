# EDA Backend v0.1

Milestone 8 adds a one-way EDA generation layer after `CircuitIR v0.1`.

```text
CircuitIR
  -> EDA Backend
  -> KiCad schematic / optional Python circuit representation / manifest
```

`CircuitIR` remains the canonical electrical state. Generated KiCad and Python representation files are derived artifacts only. Manual edits in KiCad are useful for exploration, but they do not update canonical CircuitIR in Milestone 8.

## Backend Abstraction

`EDABackend.generate(circuit_ir, context)` translates a validated `CircuitIR` into a `GenerationResult`.

The current backends are:

- `KiCadBackend`: direct `.kicad_sch` generation targeting KiCad 9.
- `PythonCircuitRepresentationBackend`: optional Python representation generated directly from CircuitIR semantics.

Both report typed `BackendCapabilities`. Round-trip support is explicitly `false`.

## KiCad Target

The KiCad backend writes a KiCad 9 schematic artifact with deterministic UUIDv5 backend IDs where practical. KiCad UUIDs are backend artifact identity only and are not copied back into CircuitIR.

The target schematic file format is KiCad S-expression schematic format with `(version 20250114)` and `generator_version "0.1"`. The version is chosen for KiCad 9 output compatibility; the backend checker still parses the generated artifact independently rather than assuming the string makes the file valid.

The backend uses local KiCad knowledge only when CircuitIR already carries a verified `SymbolReference` or `FootprintReference`. Library discovery remains a Milestone 5 knowledge concern through `KICAD9_SYMBOL_DIR` and `KICAD9_FOOTPRINT_DIR`; tests and examples can pass an explicit fixture symbol directory through `GenerationContext.kicad_symbol_dir`.

## Symbol Resolution

Symbol resolution is strict:

- verified `SymbolReference` plus loadable symbol definition -> embed the referenced KiCad symbol and use its pin geometry,
- resolved component without verified symbol -> diagnostic and placeholder,
- verified reference whose source symbol definition cannot be loaded -> diagnostic and placeholder,
- unresolved component -> editable placeholder where safe.

The backend never invents a KiCad library, symbol name, or similar replacement.

Loaded KiCad symbols are embedded by preserving the trusted source symbol subtree and applying only the required top-level/nested symbol-name rewrite to `Library:Symbol`. Milestone 8 intentionally supports simple single-unit, single-style symbols only. Multi-unit symbols and alternate-style symbols fall back to placeholders with an `unsupported_symbol_variant` diagnostic.

## Pin Mapping Trust

Pin mapping is a trust boundary. Real-symbol pin mapping is used only when CircuitIR already contains resolved pins with explicit pin numbers for represented pins and the embedded symbol definition actually contains those pins.

If exact mapping is unavailable, generation falls back to a placeholder when possible and emits an `unresolved_pin_mapping` diagnostic. It does not connect guessed symbol pins.

Placeholder pins come only from known CircuitIR logical pins. They are functional labels, not claimed package pinouts.

## Generated Pin Endpoints

Milestone 8 introduces explicit generated pin endpoints:

```text
CircuitIR component/pin
  -> generated symbol UUID
  -> KiCad pin number or placeholder pin label
  -> symbol placement/orientation
  -> exact connection point
```

Placeholder endpoints are derived from the placeholder symbol geometry at the time the placeholder symbol is generated. Real-symbol endpoints are derived from the loaded embedded KiCad symbol definition plus deterministic symbol placement. Rotation and mirroring are intentionally not varied in v0.1; generated symbols use fixed orientation `0`, so unsupported transforms cannot silently produce wrong coordinates.

## Footprints

Footprint resolution is separate from symbol resolution. Missing footprints are reported with `missing_footprint` diagnostics but do not block schematic generation by themselves.

## Placeholders

Placeholders are ordinary KiCad symbol objects with editable properties, pins, and visible unresolved/placeholder status. Their pins participate in the same endpoint resolver as real symbols. They are traceable in the manifest:

```text
PLACEHOLDER_U_REG_001
  -> CircuitIR instance U_REG_001
  -> unresolved reason
  -> known CircuitIR pin IDs and labels
```

## Connectivity

CircuitIR nets are authoritative. KiCad connectivity is actual generated electrical connectivity, not manifest metadata and not freestanding notes. For each connected CircuitIR pin, the backend places a deterministic net label at the actual generated pin endpoint. The electrical net label uses the canonical CircuitIR `net_id`, which prevents accidental merging of friendly names or ground-like roles.

Generated manifest metadata records the expected net-to-pin connectivity from CircuitIR, but the artifact checker reconstructs connectivity from the emitted `.kicad_sch` itself. Ground-like nets such as `GND`, `AGND`, and `DGND` remain separate unless CircuitIR explicitly connects them.

`no_connect` pins are emitted distinctly from `unresolved` pins. No-connect markers are placed at exact generated pin endpoints. An unresolved pin is never converted into an intentional no-connect.

## Layout

`SchematicLayoutStrategy` owns presentation geometry. It uses deterministic, simple left-to-right placement with grouping hints from CircuitIR groups and source blocks. Geometry is not written back to CircuitIR.

## Generation Result

`GenerationResult.status` has three states:

- `success`: a generated schematic exists, parses, is structurally coherent for every represented placed symbol, matches CircuitIR translated components/connectivity/no-connects, and has no placeholders, unresolved objects, or blocking diagnostics.
- `partial`: a generated schematic exists, parses, is structurally coherent for every represented placed symbol, and is electrically faithful for represented objects, but placeholders or non-blocking unresolved backend details remain.
- `failed`: no trustworthy schematic artifact was produced, or the artifact checker detects parse failure, placed-symbol corruption, symbol/path mismatch, missing/extra pin instances, missing endpoints, wrong connectivity, unintended net merge, or no-connect corruption.

This status does not imply electrical verification.

## Artifact Checker

`KiCadArtifactChecker` is a generated-artifact structural and electrical-graph checker. It parses the emitted `.kicad_sch`, validates the root `kicad_sch` form, KiCad 9 schematic version `20250114`, `schematic_ai` generator, UUID syntax, required root sections, root `sheet_instances`, embedded symbol definitions, placed symbol instances, `symbol_instances` entries, refdes/value properties, pin endpoint metadata, placeholders, labels, junctions, wires, and no-connect markers.

Structural validation runs before graph comparison. The manifest can state what the backend expected, but it cannot repair or replace missing artifact structure. If the placed symbol, pin records, unit, path, reference, value, or library identity is absent or incoherent in the `.kicad_sch`, the artifact is invalid even when manifest metadata still contains the intended mapping. Any structural failure forces both `ArtifactCheckResult.valid = false` and final `GenerationResult`/manifest status to `failed`.

Every raw top-level placed `(symbol ...)` is enumerated before field validation. Parsing records explicit raw, parsed, and malformed counts and enforces `raw_count == parsed_count + malformed_count`; valid artifacts additionally require `raw_count == parsed_count` and no malformed records. Missing `lib_id`, UUID, or `at`, and malformed X, Y, or orientation values produce structural diagnostics instead of silently removing the symbol from validation.

For every represented CircuitIR component, the checker requires exactly one placed KiCad symbol. Malformed expected symbols, malformed unexpected symbols, duplicate placed symbols, unexpected extra placed symbols, missing placed symbols, duplicate placed symbol UUIDs, and symbol UUIDs that disagree with component object mappings are rejected. This applies equally to real resolved symbols and editable placeholders.

For the supported Milestone 8 subset, each placed symbol must use `(unit 1)`, orientation `0`, a valid unique symbol UUID, a matching `lib_id`, required `Reference` and `Value` properties, `CircuitIR_ID`, and the expected placeholder/resolved status property. The expected value is the same backend-rendered display value used during generation, including placeholder display values.

Placed pin instance records are required. The checker derives the expected pin-number set from the exact embedded symbol definition selected by the placed symbol `lib_id` and compares it to the placed symbol's `(pin "<number>" (uuid "..."))` records. Missing pins, extra pins, duplicate pin numbers, missing pin UUIDs, malformed pin UUIDs, duplicate pin UUIDs, and pins not present in the selected definition are rejected.

Every placed symbol UUID must have exactly one matching `symbol_instances/path` entry of the form `/<symbol_uuid>`. The path UUID must parse as a UUID and equal the placed symbol UUID. Missing paths, duplicate paths, orphan paths, malformed path UUIDs, and paths pointing to the wrong symbol are rejected. For the supported KiCad 9 grammar, a path contains only `reference`, `unit`, `value`, and an optional `footprint`; unknown or duplicate fields are rejected. Path reference, value, unit, and footprint must agree with the placed symbol.

`lib_id` belongs to the native placed `(symbol ...)`, not to `symbol_instances/path`. Library identity is checked by relating that placed `lib_id` to the exact embedded symbol definition, the CircuitIR-backed expected representation, and the component's manifest object mapping. Application-specific source and library traceability remains in manifest metadata rather than private `.kicad_sch` path fields.

The reconstructed graph contains coordinate nodes, wire edges, pin endpoints, explicit junctions, labels as a multimap/set, no-connect points, and connected components. Wire segments are split at pins, labels, no-connects, and junctions that lie on the segment. Connected components are built with a disjoint-set union over wire edges and same-name global labels.

The checker compares connected components against CircuitIR nets and detects missing endpoint connections, extra endpoint connections, split nets, merged nets, conflicting labels/net aliases, unintended `GND`/`AGND` style merges, accidental no-connect markers, and no-connect pins that are also wired or label-connected.

The checker uses manifest object mappings only for identity normalization, such as mapping a generated net label back to a CircuitIR `net_id`. It does not accept manifest connectivity as proof that the schematic is connected.

The checker is translation fidelity validation only. It is not ERC, circuit verification, requirement PASS/FAIL, simulation, or a KiCad-to-CircuitIR importer.

## Manifest

`GeneratedArtifactManifest` records source circuit identity/revision, backend/version, generated files, object mappings, placeholders, unresolved objects, warnings, errors, status, and semantic metadata. Component mappings include the generated symbol UUID, placed `lib_id`, and trusted source path when available.

Object mappings keep backend identity separate from canonical identity:

```text
CircuitIR component instance -> KiCad symbol UUID + placed lib_id
CircuitIR net ID             -> generated KiCad label identity
```

Manifest status is written after artifact checking, so `generation_status` agrees with final `GenerationResult.status`.

## SKiDL Scope

The previous optional `SKiDLBackend` name has been reclassified. The implemented optional artifact is `PythonCircuitRepresentationBackend`, a Python file containing a deterministic CircuitIR-derived representation. It is not claimed to be executable SKiDL circuit construction because it does not use genuine SKiDL `Part`, `Net`, and connection constructs. KiCad generation remains independent of this optional representation.

## Exclusions

Milestone 8 does not implement:

- localhost web app,
- schematic viewer UI,
- CircuitIR editing UI,
- KiCad-to-CircuitIR round trip,
- schematic importer or diff,
- ERC orchestration,
- verification reports,
- SPICE simulation verification,
- repair planning,
- PCB placement, routing, or generation.
