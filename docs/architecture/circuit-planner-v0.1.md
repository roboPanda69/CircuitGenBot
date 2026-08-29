# Circuit Planner v0.1

Milestone 7 adds the first circuit synthesis layer. It converts a validated planning context into canonical `CircuitIR v0.1` through a draft-only LLM boundary and deterministic enrichment.

## Inputs

`CircuitPlanningContext` contains:

- `RequirementModel`
- `DesignPlan`
- `KnowledgeContext`
- optional existing `CircuitIR`
- optional forced component constraints
- planning metadata and configuration

The `DesignPlan` remains the primary architecture source. The planner does not bypass it or invent a different architecture from requirements alone.

## Draft Boundary

The LLM proposes only `CircuitIRDraft` JSON. Draft IDs such as `regulator`, `input_cap`, `GPIO21`, or `NET_5V` are temporary references. They are validated, evaluated, and then converted into canonical CircuitIR objects by deterministic code.

Canonical ownership stays with `CircuitIREnricher`:

- `instance_id`
- `pin_id`
- `net_id`
- `mapping_id`
- `decision_id`
- `assumption_id`
- revision
- source linkage

Reference designators such as `U1`, `C1`, `L1`, and `R1` are allocated after canonical component identity is known. New refdes assignment follows sorted canonical instance identity, and continuing refdes are preserved during refinement.

## Progressive Synthesis

The planner may return a partial but valid CircuitIR. This is successful progress when unresolved implementation state is explicit.

Example:

```text
BLOCK_PWR_001
  -> U_PWR_001 resolved to a known ComponentRecord
  -> C_001 unresolved input capacitor role
  -> C_002 unresolved output capacitor role
  -> L_001 unresolved inductor role
  -> explicit VIN, VOUT, and GND nets
```

Later refinement with new knowledge can produce a new CircuitIR revision while preserving stable object IDs where the same logical object continues to exist.

## Knowledge Loop

Milestone 7 consumes supplied `KnowledgeContext` records and exposes deterministic `KnowledgeQuery` construction for component roles. It does not create, import, crawl, or enrich knowledge records; that remains Milestone 5 ownership.

Known `ComponentRecord` IDs may be selected only if they exist in the supplied knowledge context. Fake or unknown IDs proposed by an LLM draft are rejected and enter the bounded repair loop.

A draft `proposed_component_record_id` is only a suggestion. It never becomes canonical by itself. Canonical `component_record_id` is written only from a deterministic candidate evaluation whose eligibility is `eligible` or `preferred`.

## Candidate Evaluation

`ComponentCandidateEvaluation` records explainable eligibility:

- `preferred`
- `eligible`
- `unknown`
- `rejected`

It keeps explicit satisfied constraints, preference matches, unresolved constraints, rejection reasons, and evidence IDs. Numeric scoring is intentionally absent in v0.1.

Candidate compatibility means only that the supplied Engineering Knowledge supports a candidate against known planner constraints. It is not electrical verification.

Selection is deterministic and independent of `KnowledgeContext` record order. The planner evaluates matching records, prefers `preferred` over `eligible`, and then uses stable `component_record_id` ordering. Candidates classified as `unknown` or `rejected` cannot resolve canonical components.

## Hard Vs Preferred

Hard constraints can reject or block a candidate. For example, an AEC-Q100 hard qualification requires verified AEC-Q100 evidence; unknown evidence remains unknown, and verified-no evidence rejects the candidate.

Preferences do not become hard requirements. ISO 26262 support may be preferred; a candidate with unknown ISO evidence can remain eligible while recording an unsatisfied preference.

Unknown facts remain unknown. Missing current capability is not converted into assumed current capability.

Hard constraints fail closed. Unknown current capability, missing required qualification evidence, or verified-negative compliance evidence leaves the component unresolved and records a structured planning issue.

## No Candidate

If no eligible candidate is available, the planner does not invent one. It returns a valid partial CircuitIR with unresolved component instances plus structured issues and open implementation decisions.

`knowledge_missing` means supplied knowledge is absent or insufficient. `no_candidate` means known candidates were evaluated and did not satisfy hard constraints.

## Forced Components

A forced component constraint may request a specific `component_record_id` for a role or DesignPlan target.

- Known and compatible: the planner uses it.
- Known but conflicting with hard constraints: the result is `needs_input`.
- Unknown: the result is `needs_input` with a knowledge issue.

The planner does not silently substitute another component when a forced component conflicts.

Duplicate identical forced constraints are a no-op. The same role or DesignPlan target forced to different component IDs is a blocking constraint conflict.

## Pin Policy

Draft pin details are untrusted proposal data. Because Engineering Knowledge v0.1 does not define a structured pinout contract, Milestone 7 does not resolve pins from LLM-provided `pin_number`, `pin_name`, or `resolution_status` alone.

The current deterministic strategy is to downgrade unsupported pin resolution claims:

- `pin_number` is set to `null`
- `resolution_status` is `unresolved`
- connection intent may still be represented when structurally valid

Future pin resolution must come from trusted pinout knowledge, not prompt instructions.

## Supporting Roles

The planner may instantiate unresolved supporting roles required by an architecture or selected component, such as input capacitors, output capacitors, inductors, feedback resistors, or I2C pull-ups.

Engineering rules can guide these roles in a deterministic, limited way. Milestone 7 does not add a generic rule engine.

## Value Policy

Values may be resolved only with a clear basis:

- explicit requirement value
- evidence-backed knowledge value
- simple deterministic calculation with explicit inputs
- user-forced value

Otherwise values remain unresolved. No control-loop compensation, thermal optimization, EMC design, or broad analog synthesis is implemented.

Milestone 7 stores recognized value provenance in planner-side `ValueResolutionBasis` entries attached to candidate evaluations. Canonical CircuitIR receives only the validated value; arbitrary draft values and parameters are discarded.

The v0.1 implementation recognizes only conservative evidence-backed component value attributes for simple passives, such as verified capacitance, inductance, or resistance attributes. Free-form draft parameter sources are not sufficient provenance.

## Replanning

When an existing CircuitIR is supplied, the planner produces a new revision:

- same `circuit_id`
- incremented `revision`
- previous CircuitIR unchanged
- stable object IDs preserved by simple semantic matching
- continuing reference designators preserved

This supports user-imported knowledge follow-up flows where an unresolved instance can become linked to a newly available `ComponentRecord`.

Before refinement, the existing CircuitIR must belong to the current project and exact same DesignPlan lineage. A different project, different DesignPlan ID, or different DesignPlan revision returns `needs_input` and no identity is borrowed.

For Milestone 7 v0.1, refinement requires exact project, DesignPlan ID, and DesignPlan revision equality. Cross-DesignPlan-revision migration is intentionally deferred until a future explicit architecture migration contract exists.

Semantic identity is based on stable keys such as component class, implementation role, DesignPlan linkage, requirement linkage, pin function set, net role/name/power-domain linkage, mapping endpoint sets, assumption semantic topic/source/targets, open-decision topic/targets/DesignPlan linkage, interface ID, and group source-block set. Draft order, draft reference designators, MPN text, and free-form wording are not identity keys.

Assumption IDs, open implementation decision IDs, interface binding IDs, group IDs, and mapping IDs are assigned from semantic keys and preserve matching existing IDs during refinement where safe.

Draft assumptions include a controlled planner-side `semantic_topic` such as `grounding`, `connectivity`, `interface`, `value_selection`, or `implementation`. The topic is used for identity allocation without changing frozen `CircuitAssumption` v0.1. Assumption wording may change across refinement without changing identity.

Two assumption drafts with the same complete semantic identity, meaning topic, source, and target set, are rejected as ambiguous duplicates. Milestone 7 does not allocate separate canonical assumption IDs based only on different free-text statements.

## DesignPlan Coverage

Progressive synthesis may implement only part of a DesignPlan, but omitted planned architecture stays visible. The planner derives expected implementation scope from DesignPlan structure itself, including functional blocks, interfaces, power domains, block connections, and mapped DesignPlan targets.

Requirement mappings still provide traceability and severity. Hard-mapped omissions are explicit and may be blocking; soft or preferred architecture omissions are also explicit but can remain non-blocking.

Coverage requires actual circuit implementation evidence: component source DesignPlan references, implementation mappings with circuit endpoints, generated interface bindings, net/power-domain linkage, or group source-block linkage. Open implementation decisions and assumptions can explain unresolved work, but they do not count as implementation coverage and cannot hide an omission.

Partial coverage does not mean failure. It means the returned CircuitIR is valid progressive synthesis rather than a complete implementation of the full architecture.

## Result Status

`CircuitPlanningResult.status` has four meanings:

- `accepted`: valid canonical CircuitIR with implementation status resolved for planner scope
- `partial`: valid canonical CircuitIR with explicit unresolved implementation state
- `needs_input`: progress is blocked by missing user, architecture, or knowledge decision
- `failed`: structured-output repair or planner execution failed

No status means electrical verification passed. Verification remains a future milestone.

`CircuitPlanningResult` enforces cross-field invariants: `accepted` requires resolved CircuitIR and no blocking issues; `partial` requires CircuitIR with non-resolved implementation status; `needs_input` requires a blocking issue; `failed` cannot carry CircuitIR. A resolved CircuitIR plus warnings is not `partial`.

## Repair

The planner uses the existing bounded structured-output retry style:

```text
LLM draft
  -> draft validation
  -> candidate and knowledge checks
  -> deterministic enrichment
  -> CircuitIR validation
  -> DesignPlan contextual validation
  -> Knowledge contextual validation
  -> repair prompt if planner-caused invalidity is repairable
```

The default repair budget comes from `LLM_MAX_REPAIR_ATTEMPTS`.

## Exclusions

Milestone 7 does not implement:

- KiCad, SKiDL, or SPICE generation
- EDA backend geometry or UUIDs
- ERC, simulation, thermal, stability, EMC, or electrical PASS/FAIL verification
- repair planning or learning
- PCB placement, routing, or layout
- frontend or manual schematic editing
- MCU selection
