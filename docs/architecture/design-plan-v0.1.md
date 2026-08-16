# DesignPlan v0.1 Architecture Note

## Decisions

1. DesignPlan is functional architecture, not electrical implementation.
   It describes blocks, logical ports, power domains, interfaces, and architecture decisions. It does not describe parts, pins, symbols, footprints, nets, or component values.

2. DesignPlan references one source RequirementModel revision.
   The source reference contains `requirement_set_id` and `revision`. RequirementModel revision and DesignPlan revision are independent.

3. Functional topology class is controlled architecture vocabulary.
   A block may say `switching_step_down`, `linear_regulation`, or `interface_bridge` when that is an architectural choice. Specific component identifiers such as regulator part numbers are not valid topology classes.

4. Specific components are prohibited.
   Component selection belongs to later milestones. DesignPlan v0.1 deliberately has no fields for manufacturer, MPN, symbol, footprint, pin number, net name, or SPICE model.

   Structured architecture decisions and open-decision options also use controlled architecture-level vocabularies. Free-form prose may explain a decision in `rationale` or `description`, but canonical structured choices may not encode components, values, pins, nets, symbols, or footprints.

5. Functional ports are not electrical pins.
   Ports represent logical architecture inputs and outputs such as protected power, regulated output, or an I2C bus role.

6. Block connections are not electrical nets.
   Connections describe functional flow or relationships between block ports. CircuitIR will later own electrical connectivity.

7. Power domains and interfaces are first-class.
   They are architectural objects because power and communication structure affect planning before component selection.

8. RequirementMapping is authoritative traceability.
   Functional blocks do not own requirement coverage. The plan-level `requirement_mappings[]` list is the source of truth.

   Every active hard requirement must have an explicit mapping disposition. Active means every hard requirement except `rejected` or `superseded`; this includes `candidate`, `needs_clarification`, `confirmed`, and `derived`. The dispositions `mapped`, `partially_mapped`, `unresolved`, and `not_applicable` all count as explicit coverage in v0.1. Richer planner semantics for `partially_mapped` are deferred to Milestone 4.

9. Missing WHAT belongs to RequirementModel.
   If user intent is missing, it should appear as a RequirementModel open question.

10. Missing HOW belongs to OpenArchitectureDecision.
    If the architecture has not selected a strategy, it belongs in DesignPlan open decisions.

11. Requirement coverage is validated contextually.
    The standalone DesignPlan contains only a source reference, so cross-contract checks live in `validate_design_plan_against_requirements(plan, requirement_model)`.

12. Cycles are not generically forbidden.
    Control and feedback loops can be valid functional architectures, so v0.1 rejects only obvious endpoint/direction errors.

13. CircuitIR remains future canonical circuit state.
    DesignPlan does not include components, pins, nets, generated KiCad state, SKiDL code, SPICE circuits, or verification results.
