# Automated Schematic Design System

This project is the foundation for a localhost, AI-assisted electronic schematic design system. The long-term direction is a workflow where user intent becomes structured requirements, requirements drive design planning, circuit revisions are generated, and deterministic verification evidence guides repair and learning.

## Current Scope

Milestone 1: `RequirementModel v0.1`

Milestone 1.1: `RequirementModel Contract Hardening`

Milestone 2: `Requirement Interpreter v0.1`

System v0.2 current scope:

Milestone 3: `DesignPlan v0.1`

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

Not implemented yet:

- Chat UI, FastAPI, KiCad/SKiDL generation, SPICE simulation, Circuit IR, component selection, learning, repair, PCB layout, or cloud deployment.

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

The LLM integration is limited to requirement interpretation. It does not perform architecture planning, component selection, KiCad lookup, circuit generation, or verification.

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

## Core Principle

The LLM will eventually translate human intent into structured engineering data, but the structured engineering data, not the LLM's prose, becomes the contract used by the rest of the system.
