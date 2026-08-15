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

AI-related serialized enum values use lowercase machine-facing names such as `ai` and `ai_assumption`. The project still has no Requirement Interpreter, RequirementDraft, Ollama client, prompts, KiCad lookup, or circuit-generation logic.
