# Engineering Knowledge Foundation v0.1

Milestone 5 establishes factual engineering knowledge for later circuit synthesis. It does not select components or assign them to a design.

## Boundary

Engineering Knowledge owns facts:

```text
FACT -> CANDIDATE -> VERIFIED CHOICE
```

Milestone 5 implements only the FACT side. Candidate ranking, component selection, CircuitIR, schematic generation, SPICE, verification, repair, and learning remain future milestones.

## ComponentRecord

`ComponentRecord` is a fact container. Its identity is based on stable factual fields:

- manufacturer
- part number
- optional variant or ordering code

`component_id` is deterministic from those identity fields. It is not LLM-generated and it is not tied to any design block. Selection fields such as `recommended_for_block`, `selected_for_design`, `ranking_score`, `best_candidate`, and `chosen_component` are rejected.

## Generic Attributes

`ComponentAttribute` uses a generic typed value model rather than many component-specific classes. Supported value shapes include exact, nominal, minimum, maximum, range, boolean, text, and enum values. Quantity values reuse the existing `Quantity` type from the RequirementModel foundation.

Attributes carry:

- conditions
- evidence references
- knowledge state
- metadata

This keeps the model broad enough for regulators, passives, sensors, ICs, connectors, and future categories without creating a full electronics ontology in v0.1.

## Provenance

`KnowledgeSource` describes the source document or local source of truth. Source types include manufacturer datasheets, reference manuals, safety manuals, application notes, standards, qualification documents, local KiCad libraries, manual entries, internal documents, and structured imports.

`Evidence` points from a fact back to a source locator such as a page, table, library entry, or manual note. LLM extraction is not itself engineering evidence. A future LLM extractor may create drafts, but canonical evidence must point to source material.

Source trust and extraction confidence are separate:

- `SourceTrustClass` describes the source, such as authoritative, curated internal, inferred, or unverified.
- `extraction_confidence` describes the extraction step, not the source authority.

If evidence uses `future_llm_draft` as the extraction method, it may remain `unverified` as draft extraction output. It cannot become `verified` unless it is anchored to a real `KnowledgeSource` and has an independent validation method such as manual review or a deterministic consistency check. LLM output cannot self-authorize engineering truth.

## Unknown Vs False

Absence of evidence is not verified false.

Examples:

- ISO 26262 support not found means unknown.
- AEC-Q100 evidence missing means unknown.
- Documentation unavailable means missing or unverified documentation.

`KnowledgeState` supports `verified`, `verified_no`, `unknown`, `conflicting`, and `unverified`. Boolean-style claims can use `verified` and `verified_no`, while incomplete knowledge remains `unknown`.

Conflicting attributes are preserved and reported. The repository does not silently overwrite a 2 A source with a 3 A source; it keeps both values and surfaces a conflict.

## Compliance

Compliance and qualification are explicit claims, not booleans.

`ComplianceClaim` records:

- standard
- claim type
- optional level
- scope
- evidence state
- source and evidence references

AEC qualification and ISO 26262 functional-safety support are separate facts. Automotive qualification does not imply functional-safety capability.

For ISO 26262, the model prefers conservative evidence-backed claims such as:

- developed according to ISO 26262
- supports target integrity level
- safety documentation available
- third-party certificate reference

It does not model a universal `component_is_asil_d = true` fact.

Claim subject identity is separate from evidence state and provenance. The semantic subject is the standard, claim type, level, and scope; the evidence state and supporting source/evidence references describe what is known about that subject. Unknown historical evidence is not erased when later verified evidence arrives. Exact duplicate claims are no-ops, multiple supporting evidence paths are preserved, and verified versus verified_no evidence is surfaced as a conflict.

## ComplianceProfile

`ComplianceProfile` stores project or user filtering intent. It can express required and preferred standards or qualifications for domains such as automotive, industrial, medical, aerospace, railway, and consumer.

Components do not know which project requirements apply to them. Components store facts; profiles store filtering intent.

## Engineering Rules

`EngineeringRule` stores rule records with category, applicability, statement, severity, sources, status, and metadata. Milestone 5 does not implement an executable rule DSL or complex electrical reasoning.

Example:

```text
I2C implementations require pull-up behavior on SDA and SCL.
```

Later milestones may execute or reason over these rules.

## KiCad Availability

`SymbolReference` and `FootprintReference` represent factual local CAD availability.

The local KiCad library is authoritative only for local-library facts such as "this symbol exists in this installation." It is not evidence that the symbol or footprint is correct for a final circuit choice.

Package identity and footprint identity are separate facts. A manufacturer package such as `VQFN-16` is not automatically identical to a KiCad footprint. If the mapping is unknown, it remains unknown.

Indexing is narrow and local:

- `.kicad_sym` files provide symbol entries.
- `.pretty` directories with `.kicad_mod` files provide footprint entries.
- Missing configured KiCad paths return no entries rather than breaking unrelated workflows.

## Import And Enrichment

`KnowledgeImportRequest` and `KnowledgeImportResult` define the import boundary for future structured files, internal documents, KiCad libraries, and user-supplied data. Milestone 5 does not implement remote internet download or broad PDF extraction.

Manual knowledge entries are allowed even without official documentation. Their default provenance is not authoritative. They can be unverified or curated internal depending on the supplied trust state.

When a new source refers to an existing manufacturer and part number, the repository enriches the existing component instead of creating a duplicate. New evidence is merged; conflicting facts are preserved and surfaced.

Import results distinguish material outcomes:

- new identity creates a component and returns `created`
- exact duplicate/no-op imports return `duplicate`
- genuinely new sources, evidence, attributes, claims, or CAD references return `updated_existing`
- conflicting facts return `needs_review` while preserving both values

For claims, an unknown-to-verified import is material enrichment and returns `updated_existing`. A repeated identical claim/evidence import is `duplicate`. Opposing claim states, such as verified and verified_no for the same subject, return `needs_review`.

## Retrieval

`KnowledgeQuery` and `KnowledgeFilter` support deterministic filtering by:

- component category
- known attributes
- required qualification claims
- required compliance claims
- preferred standards metadata
- source trust
- documentation status
- local KiCad symbol or footprint availability

Filtering does not rank or select final components.

`KnowledgeContext` packages retrieved facts for future circuit planning. Its `component_records` are retrieved records, not selected components.

The context includes the relevant provenance closure:

- returned component records
- applicable engineering rules
- `KnowledgeSource` objects referenced by returned facts
- `Evidence` objects referenced by returned facts
- unresolved knowledge and conflicts

It does not include the whole repository. Unrelated sources and evidence are excluded. If returned facts reference missing evidence or sources, context construction fails deterministically rather than silently returning incomplete trusted knowledge. `source_ids` is retained only as a derived compatibility summary of `sources`.

A no-match query returns a valid empty `KnowledgeContext`. Empty `component_records`, `sources`, `evidence`, and `source_ids` are valid when no facts are returned. Missing provenance remains an error only for included facts.

## Future Discovery

The contracts leave room for future online document discovery:

```text
ComponentRecord
  -> OnlineDocumentDiscovery
  -> DocumentCandidate[]
  -> user confirmation
  -> KnowledgeImportRequest
  -> canonical source/evidence/facts
```

Milestone 5 does not implement web search, crawling, remote download, URL trust, or automatic online ingestion. A search result is not trusted canonical knowledge.

## Exclusions

Milestone 5 explicitly excludes:

- CircuitIR
- component selection
- block-to-component assignment
- candidate ranking
- schematic generation
- SKiDL, KiCad schematic, or SPICE generation
- electrical verification
- repair planning
- learning
- PCB layout
- MCU selection
- online document discovery
