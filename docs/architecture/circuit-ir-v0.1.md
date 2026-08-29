# CircuitIR v0.1

Milestone 6 establishes `CircuitIR` as the canonical electrical representation between `DesignPlan` and future EDA outputs.

## Boundary

`CircuitIR` owns electrical implementation state:

```text
DesignPlan
  -> CircuitIR
  -> future KiCad / SKiDL / SPICE artifacts
```

KiCad symbols, footprints, SKiDL code, netlists, and SPICE decks are derived artifacts in later milestones. They are not the canonical source of electrical state.

Milestone 6 does not implement component selection, circuit planning, EDA generation, SPICE simulation, verification, repair, PCB layout, or learning.

## Top-Level Model

`CircuitIR` contains:

- schema version, circuit identity, project identity, and revision
- source DesignPlan identity and revision
- component instances
- nets and net connections
- optional interface bindings and circuit groups
- implementation mappings back to DesignPlan objects
- circuit-level assumptions and open implementation decisions
- optional knowledge references
- implementation status and metadata

The model can represent unresolved, partially resolved, and resolved implementation states. This allows future planners to save incomplete circuits without inventing false precision.

## Component Instances

`ComponentInstance.instance_id` is the canonical component identity inside the circuit. `reference_designator` is presentation only and is not used for structural identity.

Components carry a controlled component class, a freeform local role, source DesignPlan block IDs, optional source requirement IDs, pins, parameters, knowledge references, and implementation status.

Resolved components require `component_record_id`. Unresolved and partially resolved components may omit it.

Any non-null `component_record_id` is still a knowledge reference. Structural parsing does not require a knowledge repository, but optional knowledge validation checks every non-null component record reference regardless of whether the component is unresolved, partially resolved, or resolved. The same ID does not need to be duplicated in `knowledge_references[]`.

`ComponentInstance.implementation_status` is an implementation-completeness status. A component marked `resolved` must also have resolved component identity and resolved pin state. A resolved component identity alone does not prove electrical correctness.

## Pins And Nets

Pins are first-class objects. `pin_id` is independent of KiCad pin text, package pin numbers, and generated schematic presentation. A pin may carry optional `pin_number` and `pin_name`, but those are attributes rather than identity.

Each pin declares electrical type, function, resolution status, and connection state:

- `connected`
- `unresolved`
- `no_connect`

Nets are first-class objects with canonical `net_id`, optional display name, role, power-domain traceability, typed properties, and explicit connections.

Validation rejects:

- duplicate component, pin, net, mapping, assumption, decision, group, or binding IDs
- net connections to unknown components or pins
- pin ownership mismatches
- duplicate pin connections on one net
- the same pin connected to multiple nets
- pins marked `connected` but absent from every net
- pins marked `no_connect` but present on a net
- pins marked `unresolved` but present on a net

Pin connection state and net membership are bidirectionally consistent:

- `connected` means the pin appears on exactly one net
- `unresolved` means the pin appears on no net
- `no_connect` means the pin appears on no net

An unresolved pin is not explicitly connected yet. Once a pin is attached to a net, it must be marked `connected`.

Ground-like nets are not merged by name or role. `NET_GND`, `NET_AGND`, `NET_DGND`, and isolated grounds remain distinct unless a future planner explicitly connects them.

## Values

Component values, parameters, and net properties use structured values. Quantity values reuse the existing `Quantity` model from RequirementModel foundations.

Example:

```json
{
  "kind": "quantity",
  "quantity": {
    "value": 47,
    "unit": "uF"
  }
}
```

## Traceability

`ImplementationMapping` is the first-class link from architecture objects to electrical implementation objects. One DesignPlan block may map to many circuit objects, and one circuit object may trace to multiple blocks.

Mappings record:

- DesignPlan object IDs
- CircuitIR object IDs
- mapping type such as `implements`, `protects`, `interfaces`, `biases`, or `filters`
- implementation status
- optional rationale

Every `ImplementationMapping` must contain at least one DesignPlan-side object and at least one CircuitIR-side object. Empty placeholder mappings are rejected in v0.1 because they do not express traceability.

Source block IDs on component instances and groups provide additional direct traceability.

## Knowledge References

`KnowledgeReference` points to component records, sources, and evidence. It deliberately does not embed `KnowledgeContext`; downstream consumers can validate against a supplied context when they need provenance closure.

The optional knowledge validator checks that every non-null `ComponentInstance.component_record_id`, every `KnowledgeReference.component_record_id`, and referenced sources and evidence exist in the supplied `KnowledgeContext`. It does not decide whether a component is suitable for the circuit.

## Implementation Status

`implementation_status` describes how complete the explicit CircuitIR state is. It is not a verification result.

A top-level `CircuitIR` marked `resolved` cannot contain known unresolved or partial implementation state, including:

- unresolved or partially resolved components
- component implementation statuses that are unresolved or partial
- unresolved or partially resolved pins
- unresolved pin connections
- partial or unresolved implementation mappings
- blocking open implementation decisions

`partial` may contain a mixture of resolved, partially resolved, and unresolved objects. `unresolved` remains valid for early-stage CircuitIR.

An open implementation decision is not an electrical verification failure. However, if an open decision is marked `blocking`, the whole CircuitIR cannot claim resolved implementation completeness.

## Validation Layers

Structural validation is built into the Pydantic domain model and runs whenever `CircuitIR` is parsed.

Contextual validation is explicit:

```text
validate_circuit_ir_against_design_plan(circuit_ir, design_plan)
validate_circuit_ir_against_knowledge(circuit_ir, knowledge_context)
```

The DesignPlan validator checks source identity, source revision, source block IDs, interface references, power-domain references, implementation mapping references, and open-decision DesignPlan references.

The KnowledgeContext validator checks all non-null component record references and provenance references only.

## Example And Schemas

Validate the example:

```powershell
$env:PYTHONPATH='src'
python scripts/validate_circuit_ir_example.py
```

Generate schemas:

```powershell
$env:PYTHONPATH='src'
python scripts/export_circuit_ir_schema.py
```
