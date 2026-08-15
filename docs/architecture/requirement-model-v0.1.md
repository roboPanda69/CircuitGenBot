# RequirementModel v0.1 Architecture Note

## Decisions

1. Requirement Model is separate from Circuit IR.
   `RequirementModel` captures what the electronic system must do. It does not store KiCad state, SKiDL code, generated circuit topology, or revision verification outcomes.

2. Requirements are primarily a flat typed collection.
   This supports future queries such as all required requirements, all unconfirmed requirements, all user-originated requirements, and all requirements needing simulation.

3. Explicit requirements, assumptions, derived requirements, questions, and conflicts are distinguishable.
   These concepts have different lifecycles and should not be collapsed into one prose list.

4. Verification expectations belong here; verification outcomes do not.
   Requirements can state expected evidence methods. PASS/FAIL/WARNING results belong to a future `VerificationReport` tied to a circuit revision.

5. Engineering quantities are structured.
   Quantities use numeric values and units rather than strings such as `5V`, preserving a path to future unit normalization.

6. Provenance is preserved.
   Origins distinguish user requests from derived rules, defaults, AI assumptions, datasheets, and imports.

7. The schema is versioned.
   Serialized models include `schema_version = "0.1"` and load boundaries reject unsupported versions.

8. AI-specific behavior is not embedded into the domain contract.
   Current LLM and KiCad path choices live in configuration, not the requirement models.

9. The schema avoids becoming a full electronics ontology in v0.1.
   Categories are controlled, but requirement `type` remains extensible.

## Milestone 1.1 Hardening

Canonical requirement models should be replaced by newly validated instances rather than mutated casually in place. The small update service applies controlled patches to serialized model state, increments the requirement-set revision when the patch changes canonical data, updates `metadata.updated_at`, and reconstructs a full `RequirementModel` so all Pydantic and cross-object validation runs again.

Identity validation now covers the effective requirement namespace, assumptions, open questions, and conflicts. Reference validation rejects unknown references, repeated conflict members, duplicate `derived_from` entries, and direct self-dependencies. Full dependency-cycle analysis remains intentionally deferred to a later semantic-analysis layer.

Unit normalization is a boundary utility for future ingestion. It normalizes known spellings and aliases such as `volts` to `V` and `milliamps` to `mA`, but it does not perform magnitude conversion or dimension checking. Unknown aliases raise an explicit normalization error.

AI-related serialized enum values use lowercase machine-facing names such as `ai` and `ai_assumption`. KiCad lookup, circuit-generation logic, and later planning layers remain outside the requirement contract.

## Milestone 2 Interpreter Boundary

Milestone 2 adds the first `User Message -> RequirementModel` application layer. The LLM returns a typed draft contract, not canonical engineering state. Drafts are validated, units are normalized through the Milestone 1.1 unit boundary, and deterministic enrichment assigns IDs, provenance, defaults, verification expectations, and metadata before constructing a canonical `RequirementModel`.

The LLM boundary is replaceable via `LLMClient`. `OllamaClient` is the first backend and uses the configured local model, currently `qwen-coder`, but domain models do not import or depend on Ollama.

Follow-up messages use `RequirementChangeDraft` operations. Constraint replacements preserve requirement IDs, additions allocate new deterministic IDs, removals use the safe update path, and ambiguous edits should return open questions rather than guessed changes.

Accepted interpreter results require meaningful extracted engineering intent. If initial extraction produces no requirements and no open questions, deterministic enrichment adds a generic blocking clarification question so the result cannot be accepted as a useful model.

Follow-up questions are canonical state. When a change draft asks a new structured question, that enriched question is inserted through the safe update path into the new `RequirementModel` revision while existing open questions are preserved and question IDs remain sequential.

The repair loop is bounded. Invalid LLM structured output can be sent back for correction, but retry exhaustion raises a typed interpreter error and never returns a partially valid canonical model.

Deferred layers remain out of scope: architecture planning, engineering rules, component selection, Circuit IR, KiCad/SKiDL/SPICE generation, verification reports, repair planning, learning, and UI.
