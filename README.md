# Automated Schematic Design System

This project is the foundation for a localhost, AI-assisted electronic schematic design system. The long-term direction is a workflow where user intent becomes structured requirements, requirements drive design planning, circuit revisions are generated, and deterministic verification evidence guides repair and learning.

## Current Scope

Milestone 1: `RequirementModel v0.1`

Milestone 1.1: `RequirementModel Contract Hardening`

Milestone 2: `Requirement Interpreter v0.1`

System v0.2 frozen scope:

Milestone 3: `DesignPlan v0.1`

Milestone 4: `Architecture Planner v0.1`

System v0.3 current scope:

Milestone 5: `Engineering Knowledge Foundation v0.1` — frozen

Milestone 6: `CircuitIR v0.1`

Milestone 7: `Circuit Planner v0.1` — not started

Implemented now:

- Strongly typed Python domain models for requirements.
- Structured quantities, constraints, tolerances, conditions, assumptions, derived requirements, questions, conflicts, and verification expectations.
- JSON serialization/deserialization and generated JSON Schema.
- Example data for a temperature sensor board.
- Lightweight project settings for the current local tool choices.
- Controlled non-mutating update patches that produce newly validated requirement models.
- Deterministic unit spelling normalization for ingestion boundaries.
- Stronger identity, reference, enum, and metadata validation.
- A programmatic requirement interpreter that converts LLM structured drafts into validated canonical `RequirementModel` instances.
- Replaceable LLM client boundary with an Ollama adapter for local `qwen-coder`.
- Strongly typed `DesignPlan v0.1` models for functional architecture.
- Contextual validation that checks DesignPlan traceability against a source RequirementModel revision.
- An architecture planning application service that asks an LLM for a temporary `DesignPlanDraft`, then deterministically enriches it into a canonical `DesignPlan`.
- Basic replanning support that preserves the existing design plan identity and stable functional block identities where practical.
- Strongly typed Engineering Knowledge v0.1 contracts for component facts, sources, evidence, compliance claims, engineering rules, KiCad CAD references, imports, queries, and knowledge contexts.
- Deterministic in-memory knowledge repository behavior for identity matching, non-destructive enrichment, conflict surfacing, manual entries, and retrieval filtering.
- Narrow local KiCad symbol/footprint indexing for factual CAD availability.
- Strongly typed `CircuitIR v0.1` contracts for canonical electrical implementation state.
- First-class component instances, pins, nets, net connections, implementation mappings, assumptions, open implementation decisions, groups, and interface bindings.
- Structural CircuitIR validation for duplicate IDs, dangling references, pin ownership, bidirectional pin/net consistency, no-connect semantics, implementation completeness consistency, and pins connected to multiple nets.
- Contextual CircuitIR validation against source `DesignPlan` traceability and optional `KnowledgeContext` provenance, including every non-null component record reference.

Not implemented yet:

- Chat UI, FastAPI, KiCad/SKiDL generation, SPICE simulation, component selection, circuit planning, learning, repair, PCB layout, or cloud deployment.

## Local Tool Settings

The project currently assumes local KiCad 9 libraries and an Ollama model:

- `KICAD9_FOOTPRINT_DIR`
- `KICAD9_SYMBOL_DIR`
- `OLLAMA_HOST`, default `http://localhost:11434`
- `OLLAMA_MODEL`, default `qwen-coder`
- `LLM_MAX_REPAIR_ATTEMPTS`, default `2`

These are read in `schematic_ai.config` and deliberately kept outside the domain models.

## Install

```powershell
python -m pip install -e .[dev]
```

If using the bundled Codex runtime on this machine:

```powershell
& 'C:\Users\LENOVO\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip install -e .[dev]
```

## Run Tests

The tests use the standard library test runner so they work without installing extra test packages:

```powershell
python -m unittest discover -s tests
```

## Generate JSON Schema

```powershell
python scripts/export_requirement_schema.py
```

This writes:

```text
schemas/requirement_model_v0_1.schema.json
```

## Validate The Example

```powershell
python scripts/validate_example.py
```

The example lives at:

```text
examples/requirement_model_v0_1.json
```

## Milestone 1.1 Policies

`RequirementModel` instances are canonical engineering intent. Application code should create a new validated model through `RequirementUpdateService.apply_patch(...)` instead of casually mutating nested lists such as `requirements.append(...)`.

Unit normalization is an explicit boundary for future ingestion layers. `normalize_unit(...)` maps known spellings such as `volts` to `V`, but it does not perform physical conversion such as `500 mA` to `0.5 A`. Unknown unit aliases are rejected by the normalizer.

Identity and reference integrity are enforced across requirements, assumptions, open questions, and conflicts. Direct self-dependencies, duplicate enum choices, duplicate conflict members, invalid references, and metadata where `updated_at` precedes `created_at` are rejected.

The LLM integration is limited to requirement interpretation and architecture draft proposal. It does not perform component selection, KiCad lookup, circuit generation, or verification.

## Milestone 2 Interpreter

The interpreter does not ask the LLM to emit canonical `RequirementModel` JSON. Instead:

```text
User message
  -> LLMClient
  -> RequirementExtractionDraft or RequirementChangeDraft
  -> deterministic unit normalization
  -> deterministic enrichment
  -> canonical RequirementModel validation
```

For follow-up messages, the LLM emits change drafts such as add, replace constraint, remove, or ask an open question. The interpreter applies real requirement changes through the safe update service so the original model is not mutated and the revision increments.

An accepted interpreter result must contain meaningful extracted engineering intent. Empty extraction with no requirements and no questions becomes `needs_input` with a deterministic clarification question instead of being accepted.

Structured open questions introduced by follow-up messages are persisted into the new canonical `RequirementModel` revision. The chat-visible interpretation state and canonical model state should stay in agreement.

Ollama support is available through `OllamaClient`, but normal tests use fake LLM clients and do not require a running Ollama server.

Manual Ollama smoke test:

```powershell
$env:PYTHONPATH='src'
python scripts/test_ollama_requirement_interpreter.py
```

This requires Ollama to be running locally with the configured model available.

## Milestone 3 DesignPlan

`RequirementModel` says what the electronic system must accomplish. `DesignPlan` says what functional architecture is intended to accomplish it. Future `CircuitIR` will say how that architecture is electrically implemented.

`DesignPlan v0.1` can represent functional blocks, logical ports, block connections, power domains, interfaces, requirement mappings, architecture decisions, design assumptions, and open architecture decisions. It may use a controlled architectural `topology_class` such as `switching_step_down`, but it must not choose specific parts, symbols, footprints, pins, electrical nets, resistor values, capacitor values, or SPICE models.

Structured architecture choices use controlled vocabularies too. `ArchitectureDecision.choice` and `OpenArchitectureDecision.options[]` can contain choices such as `switching_step_down`, `direct_interface`, or `interface_bridge`, but not component names, MPNs, values, GPIO pins, nets, KiCad symbols, or footprints.

Traceability is plan-level: `requirement_mappings[]` is the authoritative structure. A contextual validator checks a `DesignPlan` against the referenced `RequirementModel` and requires every active hard requirement to have an explicit disposition. Active means hard requirements except `rejected` or `superseded`; `mapped`, `partially_mapped`, `unresolved`, and `not_applicable` all count as explicit v0.1 dispositions.

Missing WHAT the user requires remains a `RequirementModel.open_questions` concern. Missing HOW the architecture should proceed belongs in `DesignPlan.open_decisions`.

Validate the DesignPlan example:

```powershell
$env:PYTHONPATH='src'
python scripts/validate_design_plan_example.py
```

Generate its schema:

```powershell
$env:PYTHONPATH='src'
python scripts/export_design_plan_schema.py
```

## Milestone 4 Architecture Planner

`ArchitecturePlanner` is the first application service that bridges `RequirementModel` to `DesignPlan`. It preserves the frozen boundary:

```text
RequirementModel
  -> LLMClient proposes DesignPlanDraft JSON
  -> DesignPlanEnricher creates canonical DesignPlan
  -> DesignPlan contextual validation against RequirementModel
  -> direct semantic consistency checks
```

The draft is temporary and LLM-facing. It uses draft references such as `b_converter`, `vout_main`, or even arbitrary labels such as `TPS54331`; canonical IDs such as `BLOCK_PWR_001`, `PWRDOM_001`, `PORT_PWR_001`, `CONN_001`, and `MAP_001` are assigned only by deterministic code and do not derive from draft IDs.

Canonical planner-owned text is also deterministic. Raw LLM names, purposes, rationales, descriptions, assumptions, and open-decision prose are not copied unchanged into canonical `DesignPlan` state; architecture-level text is generated from structured fields such as block type, topology class, power-domain role, interface type, architecture choice, and mapped requirements.

Milestone 4 performs small direct semantic checks after normal DesignPlan validation. It currently checks mapped voltage facts and mapped interface protocol facts, for example rejecting a 5 V requirement mapped to a 3.3 V power domain or an I2C requirement mapped to an SPI interface. This is not electrical verification and does not prove output current capability, component feasibility, thermal behavior, signal integrity, or implementation correctness.

Planner result statuses:

- `accepted`: a valid `DesignPlan` is available.
- `needs_input`: a blocking requirement question exists, no active hard requirements exist, or the enriched plan contains a blocking open architecture decision.
- `failed`: the LLM draft cannot be parsed, repaired, enriched, or validated.

Missing WHAT the user requires remains a `RequirementModel.open_questions` issue. Missing HOW to structure the architecture is represented as `DesignPlan.open_decisions`. Non-blocking open architecture decisions can still produce an accepted plan; blocking ones return `needs_input` with the draft-enriched plan attached.

Run the fake-LLM planner example:

```powershell
$env:PYTHONPATH='src'
python scripts/example_architecture_planner.py
```

The example and tests do not require Ollama. Production usage can pass any object implementing the existing `LLMClient.generate_structured(...)` boundary, including the configured local Ollama `qwen-coder` client.

## Milestone 5 Engineering Knowledge

Engineering Knowledge stores factual, evidence-backed knowledge. It does not recommend, rank, choose, or assign components.

Core flow:

```text
KnowledgeSource
  -> Evidence
  -> ComponentRecord facts / EngineeringRule records
  -> KnowledgeQuery filtering
  -> KnowledgeContext for future circuit planning
```

`ComponentRecord` is a fact container keyed by stable identity fields such as manufacturer, part number, and optional variant. It contains generic `ComponentAttribute` values, qualification and compliance claims, local KiCad symbol/footprint references, documentation status, and lifecycle status. It explicitly does not contain selection fields such as ranking score, best candidate, or selected design block.

Unknown information remains unknown. Lack of ISO 26262 evidence, AEC qualification evidence, or datasheet evidence is not treated as verified false. Conflicting evidence is preserved and surfaced for review instead of destructively overwriting existing facts.

`KnowledgeContext` includes the relevant `KnowledgeSource` and `Evidence` objects for returned facts, not just source IDs, so downstream consumers can inspect provenance without extra repository lookups. LLM draft extraction cannot self-verify; verified LLM-extracted evidence requires real source grounding and an independent validation method.

Repository import results distinguish `created`, `updated_existing`, `duplicate`, and `needs_review`. Exact no-op imports return `duplicate`; real enrichment returns `updated_existing`; conflicting knowledge remains non-destructive.

No-match knowledge queries return a valid empty `KnowledgeContext`. Claim enrichment keeps claim subject separate from evidence state/provenance, so unknown-to-verified evidence is preserved as enrichment, exact duplicates are no-ops, and conflicting claim states remain visible.

Run Milestone 5 examples and schemas:

```powershell
$env:PYTHONPATH='src'
python scripts/validate_knowledge_examples.py
python scripts/export_knowledge_schemas.py
```

Local KiCad indexing uses configured `KICAD9_SYMBOL_DIR` and `KICAD9_FOOTPRINT_DIR` when no explicit fixture path is supplied. Normal tests use fixtures and do not require a user-local KiCad installation.

## Milestone 6 CircuitIR

`CircuitIR` is the canonical electrical state of the project. It sits after `DesignPlan` and before future EDA-specific artifacts:

```text
DesignPlan
  -> CircuitIR
  -> future KiCad / SKiDL / SPICE outputs
```

`CircuitIR v0.1` supports unresolved, partially resolved, and resolved component instances. Resolved components require a `component_record_id`; unresolved and partially resolved components can remain structurally valid without one. Any non-null `component_record_id` is still a knowledge reference and is checked by optional knowledge validation.

Pins and nets are first-class objects. Pin identity is independent of KiCad pin labels and package pin numbers. Nets carry explicit connections and roles such as `power`, `ground`, `signal`, `clock`, `analog`, `digital`, and `communication`. A pin on a net must be marked `connected`; unresolved and no-connect pins must appear on no net. Ground nets are not auto-merged; `GND` and `AGND` remain separate unless future planning explicitly connects them.

Traceability from architecture to circuit implementation is recorded through source block IDs and first-class `ImplementationMapping` records. Contextual validation checks CircuitIR references against a source `DesignPlan`, and optional knowledge validation checks referenced component records, sources, and evidence against a supplied `KnowledgeContext`.

`implementation_status` describes implementation completeness, not electrical correctness. A resolved CircuitIR cannot contain unresolved or partial components, unresolved pins, partial mappings, or blocking open implementation decisions. Every implementation mapping must have at least one DesignPlan-side endpoint and at least one CircuitIR-side endpoint.

Run Milestone 6 validation and schema export:

```powershell
$env:PYTHONPATH='src'
python scripts/validate_circuit_ir_example.py
python scripts/export_circuit_ir_schema.py
```

The example lives at:

```text
examples/circuit_ir_v0_1.json
```

The architecture note lives at:

```text
docs/architecture/circuit-ir-v0.1.md
```

## Core Principle

The LLM will eventually translate human intent into structured engineering data, but the structured engineering data, not the LLM's prose, becomes the contract used by the rest of the system.
