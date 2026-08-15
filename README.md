# Automated Schematic Design System

This project is the foundation for a localhost, AI-assisted electronic schematic design system. The long-term direction is a workflow where user intent becomes structured requirements, requirements drive design planning, circuit revisions are generated, and deterministic verification evidence guides repair and learning.

## Current Scope

Milestone 1: `RequirementModel v0.1`

Milestone 1.1: `RequirementModel Contract Hardening`

Implemented now:

- Strongly typed Python domain models for requirements.
- Structured quantities, constraints, tolerances, conditions, assumptions, derived requirements, questions, conflicts, and verification expectations.
- JSON serialization/deserialization and generated JSON Schema.
- Example data for a temperature sensor board.
- Lightweight project settings for the current local tool choices.
- Controlled non-mutating update patches that produce newly validated requirement models.
- Deterministic unit spelling normalization for ingestion boundaries.
- Stronger identity, reference, enum, and metadata validation.

Not implemented yet:

- LLM integration, chat UI, FastAPI, KiCad/SKiDL generation, SPICE simulation, Circuit IR, component selection, learning, repair, PCB layout, or cloud deployment.

## Local Tool Settings

The project currently assumes local KiCad 9 libraries and an Ollama model:

- `KICAD9_FOOTPRINT_DIR`
- `KICAD9_SYMBOL_DIR`
- Ollama model name: `qwen-coder`

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

There is still no LLM integration. Ollama and `qwen-coder` remain configuration defaults only.

## Core Principle

The LLM will eventually translate human intent into structured engineering data, but the structured engineering data, not the LLM's prose, becomes the contract used by the rest of the system.
