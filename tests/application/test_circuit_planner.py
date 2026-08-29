import copy
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from schematic_ai.application.circuit_planner import (
    CandidateEligibility,
    CircuitAssumptionTopic,
    CircuitCandidateEvaluator,
    CircuitIRDraft,
    CircuitPlanner,
    CircuitPlannerConfiguration,
    CircuitPlanningIssue,
    CircuitPlanningResult,
    CircuitPlanningContext,
    CircuitPlanningStatus,
    DraftComponentInstance,
    ForcedComponentConstraint,
    knowledge_query_for_component,
)
from schematic_ai.domain.circuit_ir import (
    CircuitIR,
    CircuitComponentRole,
    validate_circuit_ir_against_design_plan,
    validate_circuit_ir_against_knowledge,
)
from schematic_ai.domain.design_plan import DesignPlan
from schematic_ai.domain.knowledge import (
    ComponentAttribute,
    ComponentRecord,
    ComplianceClaim,
    Evidence,
    KnowledgeContext,
    KnowledgeMetadata,
    KnowledgeQuery,
    KnowledgeSource,
    QuantityExactValue,
    QuantityMaximumValue,
    QuantityRangeValue,
    quantity,
)
from schematic_ai.domain.requirements.models import RequirementModel


ROOT = Path(__file__).resolve().parents[2]
REQUIREMENT_PATH = ROOT / "examples" / "requirement_model_v0_1.json"
DESIGN_PLAN_PATH = ROOT / "examples" / "design_plan_v0_1.json"


class FakeLLMClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def generate_structured(self, *, prompt, json_schema=None):
        self.prompts.append(prompt)
        if not self.outputs:
            raise AssertionError("fake LLM has no output queued")
        return self.outputs.pop(0)


def metadata():
    return KnowledgeMetadata(created_by="planner_test")


def source(source_id="SRC_DS_001"):
    return KnowledgeSource(
        source_id=source_id,
        source_type="manufacturer_datasheet",
        title=f"Datasheet {source_id}",
        locator=f"tests/{source_id}.pdf",
        trust_class="authoritative",
        metadata=metadata(),
    )


def evidence(evidence_id="EVID_DS_001", source_id="SRC_DS_001"):
    return Evidence(
        evidence_id=evidence_id,
        source_id=source_id,
        locator="page 1 electrical characteristics",
        extraction_method="manual",
        extraction_confidence=1.0,
        validation_state="verified",
        validation_method="manual_review",
        metadata=metadata(),
    )


def attribute(attribute_id, name, value, evidence_id="EVID_DS_001"):
    return ComponentAttribute(
        attribute_id=attribute_id,
        name=name,
        value=value,
        evidence_ids=[evidence_id],
        status="verified",
        metadata=metadata(),
    )


def claim(claim_id, standard, state="verified", source_id="SRC_DS_001", evidence_id="EVID_DS_001", claim_type="qualified_to"):
    return ComplianceClaim(
        claim_id=claim_id,
        standard=standard,
        claim_type=claim_type,
        level=None,
        scope="synthetic planner fixture",
        evidence_state=state,
        source_ids=[source_id],
        evidence_ids=[evidence_id] if state != "unknown" else [],
        metadata=metadata(),
    )


def component(
    component_id="CMP_001",
    *,
    max_current=3,
    include_current=True,
    aec_state="verified",
    iso_state=None,
):
    compliance_claims = []
    if iso_state is not None:
        compliance_claims.append(
            claim("CLAIM_ISO_001", "ISO_26262", state=iso_state, claim_type="supports_target_integrity_level")
        )
    attributes = [
        attribute(
            "ATTR_VIN_001",
            "input_voltage",
            QuantityRangeValue(minimum=quantity(3, "V"), maximum=quantity(17, "V")),
        )
    ]
    if include_current:
        attributes.append(
            attribute(
                "ATTR_IOUT_001",
                "maximum_output_current",
                QuantityMaximumValue(value=quantity(max_current, "A")),
            )
        )
    return ComponentRecord(
        component_id=component_id,
        manufacturer="Synthetic Semiconductor",
        part_number=component_id.replace("CMP_", "SYN-"),
        category="power_converter",
        attributes=attributes,
        qualification_claims=[claim("CLAIM_AEC_001", "AEC_Q100", state=aec_state)],
        compliance_claims=compliance_claims,
        source_ids=["SRC_DS_001"],
        documentation_status="complete",
        lifecycle_status="active",
        metadata=metadata(),
    )


def passive_component(
    component_id="CMP_CAP_001",
    *,
    category="capacitor",
    attribute_name="capacitance",
    attribute_value=None,
):
    return ComponentRecord(
        component_id=component_id,
        manufacturer="Synthetic Passive",
        part_number=component_id.replace("CMP_", "SYN-"),
        category=category,
        attributes=[
            ComponentAttribute(
                attribute_id=f"ATTR_{component_id}_VALUE",
                name=attribute_name,
                value=attribute_value or QuantityExactValue(value=quantity(22, "uF")),
                evidence_ids=["EVID_DS_001"],
                status="verified",
                metadata=metadata(),
            )
        ],
        qualification_claims=[],
        compliance_claims=[],
        source_ids=["SRC_DS_001"],
        documentation_status="complete",
        lifecycle_status="active",
        metadata=metadata(),
    )


def knowledge_context(records=None, rules=None):
    return KnowledgeContext(
        context_id="KCTX_PLANNER_001",
        query=KnowledgeQuery(query_id="KQ_PLANNER_001", metadata=metadata()),
        component_records=records if records is not None else [component()],
        engineering_rules=rules or [],
        sources=[source()],
        evidence=[evidence()],
        metadata=metadata(),
    )


def requirement_model():
    return RequirementModel.model_validate_json(REQUIREMENT_PATH.read_text(encoding="utf-8"))


def design_plan():
    return DesignPlan.model_validate_json(DESIGN_PLAN_PATH.read_text(encoding="utf-8"))


def base_context(*, records=None, existing=None, forced=(), configuration=None):
    return CircuitPlanningContext(
        requirement_model=requirement_model(),
        design_plan=design_plan(),
        knowledge_context=knowledge_context(records),
        existing_circuit_ir=existing,
        forced_component_constraints=forced,
        configuration=configuration or CircuitPlannerConfiguration(),
    )


def context_with_models(requirements, plan, *, records=None, existing=None, forced=(), configuration=None):
    return CircuitPlanningContext(
        requirement_model=requirements,
        design_plan=plan,
        knowledge_context=knowledge_context(records),
        existing_circuit_ir=existing,
        forced_component_constraints=forced,
        configuration=configuration or CircuitPlannerConfiguration(),
    )


def planner_with_draft(draft, *, max_repair_attempts=0):
    return CircuitPlanner(FakeLLMClient([json.dumps(draft)]), max_repair_attempts=max_repair_attempts)


def base_power_draft(*, proposed_component_record_id=None, converter_resolution="unresolved", mapping_status="partial"):
    return {
        "component_instances": [
            {
                "draft_id": "TPS54331",
                "role": "main_power_converter",
                "component_class": "converter",
                "resolution_intent": converter_resolution,
                "proposed_component_record_id": proposed_component_record_id,
                "reference_designator_hint": "U99",
                "value": None,
                "parameters": [],
                "source_design_plan_refs": ["BLOCK_PWR_001"],
                "source_requirement_refs": ["REQ_PWR_001", "REQ_PWR_002", "REQ_PWR_003"],
                "pin_drafts": [
                    {
                        "draft_pin_id": "vin_pin",
                        "component_draft_id": "TPS54331",
                        "function": "input power",
                        "pin_name": "VIN",
                        "electrical_type": "power_input",
                        "resolution_status": "unresolved",
                        "connection_intent": "connected",
                    },
                    {
                        "draft_pin_id": "vout_pin",
                        "component_draft_id": "TPS54331",
                        "function": "regulated output",
                        "pin_name": "VOUT",
                        "electrical_type": "power_output",
                        "resolution_status": "unresolved",
                        "connection_intent": "connected",
                    },
                    {
                        "draft_pin_id": "gnd_pin",
                        "component_draft_id": "TPS54331",
                        "function": "ground",
                        "pin_name": "GND",
                        "electrical_type": "power_input",
                        "resolution_status": "unresolved",
                        "connection_intent": "connected",
                    },
                    {
                        "draft_pin_id": "sw_pin",
                        "component_draft_id": "TPS54331",
                        "function": "switch node",
                        "pin_name": None,
                        "electrical_type": "power_output",
                        "resolution_status": "unresolved",
                        "connection_intent": "unresolved",
                    },
                ],
            },
            support_component("input_cap", "input_decoupling", "capacitor", ["vin", "gnd"]),
            support_component("output_cap", "output_decoupling", "capacitor", ["vout", "gnd"]),
            support_component("inductor", "output_inductor", "inductor", ["vout", "sw"]),
        ],
        "nets": [
            {
                "draft_net_id": "GPIO21",
                "name_hint": "VIN",
                "role": "power",
                "power_domain_ref": "PWRDOM_VIN_PROTECTED",
                "connections": [
                    {"component_draft_id": "TPS54331", "draft_pin_id": "vin_pin"},
                    {"component_draft_id": "input_cap", "draft_pin_id": "input_cap_pin_a"},
                ],
            },
            {
                "draft_net_id": "NET_5V",
                "name_hint": "VOUT",
                "role": "power",
                "power_domain_ref": "PWRDOM_5V",
                "connections": [
                    {"component_draft_id": "TPS54331", "draft_pin_id": "vout_pin"},
                    {"component_draft_id": "output_cap", "draft_pin_id": "output_cap_pin_a"},
                    {"component_draft_id": "inductor", "draft_pin_id": "inductor_pin_a"},
                ],
            },
            {
                "draft_net_id": "gnd",
                "name_hint": "GND",
                "role": "ground",
                "connections": [
                    {"component_draft_id": "TPS54331", "draft_pin_id": "gnd_pin"},
                    {"component_draft_id": "input_cap", "draft_pin_id": "input_cap_pin_b"},
                    {"component_draft_id": "output_cap", "draft_pin_id": "output_cap_pin_b"},
                ],
            },
        ],
        "implementation_mappings": [
            {
                "draft_mapping_id": "map_power",
                "design_plan_refs": ["BLOCK_PWR_001"],
                "circuit_draft_refs": ["TPS54331", "input_cap", "output_cap", "inductor", "GPIO21", "NET_5V"],
                "mapping_type": "implements",
                "status": mapping_status,
                "rationale": "Draft maps the power block to converter and supporting roles.",
            }
        ],
        "assumptions": [],
        "open_decisions": [],
        "metadata": {},
    }


def support_component(draft_id, role, component_class, net_roles):
    return {
        "draft_id": draft_id,
        "role": role,
        "component_class": component_class,
        "resolution_intent": "unresolved",
        "proposed_component_record_id": None,
        "reference_designator_hint": "RANDOM1",
        "value": None,
        "parameters": [],
        "source_design_plan_refs": ["BLOCK_PWR_001"],
        "source_requirement_refs": [],
        "pin_drafts": [
            {
                "draft_pin_id": f"{draft_id}_pin_a",
                "component_draft_id": draft_id,
                "function": net_roles[0],
                "pin_name": None,
                "electrical_type": "passive",
                "resolution_status": "unresolved",
                "connection_intent": "connected",
            },
            {
                "draft_pin_id": f"{draft_id}_pin_b",
                "component_draft_id": draft_id,
                "function": net_roles[1],
                "pin_name": None,
                "electrical_type": "passive",
                "resolution_status": "unresolved",
                "connection_intent": "connected" if draft_id != "inductor" else "unresolved",
            },
        ],
    }


def fully_resolved_draft():
    draft = base_power_draft(proposed_component_record_id="CMP_001", converter_resolution="resolved", mapping_status="resolved")
    draft["component_instances"] = [draft["component_instances"][0]]
    for pin in draft["component_instances"][0]["pin_drafts"]:
        if pin["draft_pin_id"] == "sw_pin":
            continue
        pin["pin_number"] = {"vin_pin": "1", "vout_pin": "2", "gnd_pin": "3"}[pin["draft_pin_id"]]
        pin["resolution_status"] = "resolved"
    draft["component_instances"][0]["pin_drafts"] = [
        pin for pin in draft["component_instances"][0]["pin_drafts"] if pin["draft_pin_id"] != "sw_pin"
    ]
    draft["nets"] = [
        {
            "draft_net_id": "vin",
            "name_hint": "VIN",
            "role": "power",
            "power_domain_ref": "PWRDOM_VIN_PROTECTED",
            "connections": [{"component_draft_id": "TPS54331", "draft_pin_id": "vin_pin"}],
        },
        {
            "draft_net_id": "vout",
            "name_hint": "VOUT",
            "role": "power",
            "power_domain_ref": "PWRDOM_5V",
            "connections": [{"component_draft_id": "TPS54331", "draft_pin_id": "vout_pin"}],
        },
        {
            "draft_net_id": "gnd",
            "name_hint": "GND",
            "role": "ground",
            "connections": [{"component_draft_id": "TPS54331", "draft_pin_id": "gnd_pin"}],
        },
    ]
    draft["implementation_mappings"][0]["circuit_draft_refs"] = ["TPS54331", "vin", "vout", "gnd"]
    return draft


def all_design_scope_ids(plan=None):
    plan = plan or design_plan()
    return [
        *(block.block_id for block in plan.functional_blocks),
        *(interface.interface_id for interface in plan.interfaces),
        *(domain.power_domain_id for domain in plan.power_domains),
        *(connection.connection_id for connection in plan.block_connections),
    ]


def fully_scoped_power_draft():
    draft = base_power_draft()
    draft["implementation_mappings"][0]["design_plan_refs"] = all_design_scope_ids()
    return draft


def artificial_resolved_circuit():
    result = planner_with_draft(fully_resolved_draft()).plan_circuit(base_context())
    data = result.circuit_ir.model_dump(mode="json")
    data["implementation_status"] = "resolved"
    for component in data["components"]:
        component["resolution_status"] = "resolved"
        component["implementation_status"] = "resolved"
        for pin in component["pins"]:
            pin["resolution_status"] = "resolved"
    for mapping in data["implementation_mappings"]:
        mapping["status"] = "resolved"
    data["open_decisions"] = []
    return CircuitIR.model_validate(data)


class CircuitPlannerModelTests(unittest.TestCase):
    def test_context_and_draft_models_serialize(self):
        context = base_context()
        draft = CircuitIRDraft.model_validate(base_power_draft())
        restored = CircuitIRDraft.model_validate_json(draft.model_dump_json())

        self.assertEqual(context.design_plan.design_plan_id, "DPLAN_0001")
        self.assertEqual(restored.model_dump(mode="json"), draft.model_dump(mode="json"))

    def test_draft_rejects_unknown_pin_reference(self):
        data = base_power_draft()
        data["nets"][0]["connections"][0]["draft_pin_id"] = "missing_pin"

        with self.assertRaises(ValidationError):
            CircuitIRDraft.model_validate(data)

    def test_knowledge_query_for_component_uses_context_constraints(self):
        context = base_context(configuration=CircuitPlannerConfiguration(required_qualifications=("AEC_Q100",)))
        draft_component = DraftComponentInstance.model_validate(base_power_draft()["component_instances"][0])
        query = knowledge_query_for_component(draft_component, context)

        self.assertEqual(query.filters.category, "power_converter")
        self.assertEqual(query.filters.required_qualifications, ["AEC_Q100"])
        self.assertEqual({constraint.name for constraint in query.filters.attribute_constraints}, {"input_voltage", "maximum_output_current"})


class CircuitPlannerFlowTests(unittest.TestCase):
    def test_basic_planning_selects_known_component_and_supporting_roles(self):
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context())

        self.assertEqual(result.status, CircuitPlanningStatus.PARTIAL)
        self.assertIsNotNone(result.circuit_ir)
        selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")
        self.assertEqual(selected.component_record_id, "CMP_001")
        self.assertEqual({component.role for component in result.circuit_ir.components}, {"main_power_converter", "input_decoupling", "output_decoupling", "output_inductor"})
        validate_circuit_ir_against_design_plan(result.circuit_ir, design_plan())
        validate_circuit_ir_against_knowledge(result.circuit_ir, base_context().knowledge_context)

    def test_known_component_resolution_from_draft_is_contextually_valid(self):
        result = planner_with_draft(base_power_draft(proposed_component_record_id="CMP_001")).plan_circuit(base_context())
        selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")

        self.assertEqual(selected.component_record_id, "CMP_001")
        self.assertTrue(any(evaluation.component_record_id == "CMP_001" for evaluation in result.candidate_evaluations))

    def test_fake_component_rejection_triggers_repair_and_never_reaches_canonical(self):
        bad = base_power_draft(proposed_component_record_id="CMP_FAKE")
        good = base_power_draft(proposed_component_record_id="CMP_001")
        llm = FakeLLMClient([json.dumps(bad), json.dumps(good)])
        result = CircuitPlanner(llm, max_repair_attempts=1).plan_circuit(base_context())

        self.assertEqual(result.status, CircuitPlanningStatus.PARTIAL)
        self.assertEqual(len(llm.prompts), 2)
        self.assertFalse(any(component.component_record_id == "CMP_FAKE" for component in result.circuit_ir.components))

    def test_zero_candidates_returns_partial_without_hallucination(self):
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context(records=[]))

        self.assertEqual(result.status, CircuitPlanningStatus.PARTIAL)
        selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")
        self.assertIsNone(selected.component_record_id)
        self.assertTrue(any(issue.issue_type == "knowledge_missing" for issue in result.issues))

    def test_hard_compliance_filter_rejects_unknown_and_verified_no(self):
        context = base_context(
            records=[
                component("CMP_UNKNOWN_AEC", aec_state="unknown"),
                component("CMP_NO_AEC", aec_state="verified_no"),
                component("CMP_OK_AEC", aec_state="verified"),
            ],
            configuration=CircuitPlannerConfiguration(required_qualifications=("AEC_Q100",)),
        )
        result = planner_with_draft(base_power_draft()).plan_circuit(context)
        selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")

        self.assertEqual(selected.component_record_id, "CMP_OK_AEC")
        eligibilities = {evaluation.component_record_id: evaluation.eligibility for evaluation in result.candidate_evaluations}
        self.assertEqual(eligibilities["CMP_UNKNOWN_AEC"], CandidateEligibility.UNKNOWN)
        self.assertEqual(eligibilities["CMP_NO_AEC"], CandidateEligibility.REJECTED)

    def test_preferred_compliance_does_not_reject_candidate(self):
        context = base_context(configuration=CircuitPlannerConfiguration(preferred_compliance=("ISO_26262",)))
        result = planner_with_draft(base_power_draft()).plan_circuit(context)
        evaluation = next(item for item in result.candidate_evaluations if item.component_record_id == "CMP_001")

        self.assertIn(evaluation.eligibility, {CandidateEligibility.ELIGIBLE, CandidateEligibility.PREFERRED})
        self.assertIn("preferred_compliance:ISO_26262", evaluation.unresolved_constraints)

    def test_i2c_implementation_creates_sda_scl_without_gpio_assignment(self):
        draft = {
            "component_instances": [
                support_component("pullup_sda", "i2c_sda_pullup", "resistor", ["sda", "vcc"]),
                support_component("pullup_scl", "i2c_scl_pullup", "resistor", ["scl", "vcc"]),
            ],
            "nets": [
                {
                    "draft_net_id": "GPIO21",
                    "name_hint": "SDA",
                    "role": "communication",
                    "connections": [{"component_draft_id": "pullup_sda", "draft_pin_id": "pullup_sda_pin_a"}],
                },
                {
                    "draft_net_id": "GPIO22",
                    "name_hint": "SCL",
                    "role": "communication",
                    "connections": [{"component_draft_id": "pullup_scl", "draft_pin_id": "pullup_scl_pin_a"}],
                },
                {
                    "draft_net_id": "vcc",
                    "name_hint": "5V",
                    "role": "power",
                    "power_domain_ref": "PWRDOM_5V",
                    "connections": [
                        {"component_draft_id": "pullup_sda", "draft_pin_id": "pullup_sda_pin_b"},
                        {"component_draft_id": "pullup_scl", "draft_pin_id": "pullup_scl_pin_b"},
                    ],
                },
            ],
            "implementation_mappings": [
                {
                    "draft_mapping_id": "map_i2c",
                    "design_plan_refs": ["IF_I2C_001"],
                    "circuit_draft_refs": ["pullup_sda", "pullup_scl", "GPIO21", "GPIO22"],
                    "mapping_type": "interfaces",
                    "status": "partial",
                }
            ],
        }
        result = planner_with_draft(draft).plan_circuit(base_context())

        self.assertEqual({net.name for net in result.circuit_ir.nets}, {"SDA", "SCL", "5V"})
        self.assertFalse(any("GPIO21" in item.instance_id or "GPIO22" in item.instance_id for item in result.circuit_ir.components))
        self.assertFalse(any("GPIO21" in net.net_id or "GPIO22" in net.net_id for net in result.circuit_ir.nets))

    def test_canonical_ids_and_refdes_are_deterministic_and_llm_independent(self):
        result = planner_with_draft(base_power_draft(proposed_component_record_id="CMP_001")).plan_circuit(base_context())
        components = result.circuit_ir.components

        self.assertEqual(components[0].instance_id, "U_PWR_001")
        self.assertEqual(components[0].reference_designator, "U1")
        self.assertEqual([component.reference_designator for component in components[1:]], ["C1", "C2", "L1"])
        self.assertFalse(any(component.instance_id in {"TPS54331", "LM2596", "R1"} for component in components))
        self.assertFalse(any(net.net_id in {"GPIO21", "NET_5V"} for net in result.circuit_ir.nets))

    def test_invalid_connectivity_can_be_repaired(self):
        bad = base_power_draft()
        bad["nets"][1]["connections"] = [
            connection for connection in bad["nets"][1]["connections"] if connection["draft_pin_id"] != "vout_pin"
        ]
        good = base_power_draft()
        llm = FakeLLMClient([json.dumps(bad), json.dumps(good)])
        result = CircuitPlanner(llm, max_repair_attempts=1).plan_circuit(base_context())

        self.assertEqual(result.status, CircuitPlanningStatus.PARTIAL)
        self.assertEqual(len(llm.prompts), 2)

    def test_retry_exhaustion_returns_failed_without_canonical_circuit(self):
        bad = base_power_draft()
        bad["nets"][0]["connections"][0]["component_draft_id"] = "missing"
        result = CircuitPlanner(FakeLLMClient([json.dumps(bad), json.dumps(bad)]), max_repair_attempts=1).plan_circuit(base_context())

        self.assertEqual(result.status, CircuitPlanningStatus.FAILED)
        self.assertIsNone(result.circuit_ir)
        self.assertTrue(result.issues)

    def test_partial_result_is_successful_progressive_synthesis(self):
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context(records=[]))

        self.assertEqual(result.status, CircuitPlanningStatus.PARTIAL)
        self.assertIsNotNone(result.circuit_ir)
        self.assertEqual(result.circuit_ir.implementation_status, "partial")

    def test_fully_resolved_draft_pins_without_pinout_knowledge_remain_partial(self):
        result = planner_with_draft(fully_resolved_draft()).plan_circuit(base_context())

        self.assertEqual(result.status, CircuitPlanningStatus.PARTIAL)
        self.assertEqual(result.circuit_ir.implementation_status, "partial")
        self.assertTrue(all(pin.pin_number is None for component in result.circuit_ir.components for pin in component.pins))
        self.assertTrue(all(pin.resolution_status == "unresolved" for component in result.circuit_ir.components for pin in component.pins))
        self.assertNotIn("verification", result.diagnostics)

    def test_refinement_preserves_circuit_and_instance_ids_and_does_not_mutate_original(self):
        first = planner_with_draft(base_power_draft()).plan_circuit(base_context(records=[])).circuit_ir
        first_snapshot = first.model_dump(mode="json")
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context(existing=first))
        refined = result.circuit_ir

        self.assertEqual(refined.circuit_id, first.circuit_id)
        self.assertEqual(refined.revision, first.revision + 1)
        self.assertEqual(refined.components[0].instance_id, first.components[0].instance_id)
        self.assertEqual(refined.components[0].component_record_id, "CMP_001")
        self.assertEqual(first.model_dump(mode="json"), first_snapshot)

    def test_user_forced_component_known_and_compatible_is_used(self):
        context = base_context(
            forced=(ForcedComponentConstraint(target_role="main_power_converter", component_record_id="CMP_001"),)
        )
        result = planner_with_draft(base_power_draft()).plan_circuit(context)

        self.assertEqual(result.circuit_ir.components[0].component_record_id, "CMP_001")

    def test_user_forced_unknown_component_needs_input(self):
        context = base_context(
            forced=(ForcedComponentConstraint(target_role="main_power_converter", component_record_id="CMP_FAKE"),)
        )
        result = planner_with_draft(base_power_draft()).plan_circuit(context)

        self.assertEqual(result.status, CircuitPlanningStatus.NEEDS_INPUT)
        self.assertTrue(any(issue.issue_type == "knowledge_missing" and issue.blocking for issue in result.issues))

    def test_user_forced_component_that_violates_hard_constraint_needs_input(self):
        context = base_context(
            records=[component(max_current=1)],
            forced=(ForcedComponentConstraint(target_role="main_power_converter", component_record_id="CMP_001"),),
        )
        result = planner_with_draft(base_power_draft()).plan_circuit(context)

        self.assertEqual(result.status, CircuitPlanningStatus.NEEDS_INPUT)
        self.assertTrue(any(issue.issue_type == "constraint_conflict" and issue.blocking for issue in result.issues))

    def test_unknown_current_capability_remains_unknown(self):
        context = base_context(records=[component(include_current=False)])
        evaluation = CircuitCandidateEvaluator().evaluate(
            [DraftComponentInstance.model_validate(base_power_draft()["component_instances"][0])],
            context,
        ).evaluations[0]

        self.assertEqual(evaluation.eligibility, CandidateEligibility.UNKNOWN)
        self.assertIn("attribute:maximum_output_current", evaluation.unresolved_constraints)

    def test_candidate_evaluation_retains_evidence_ids(self):
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context())
        evaluation = next(item for item in result.candidate_evaluations if item.component_record_id == "CMP_001")

        self.assertIn("EVID_DS_001", evaluation.evidence_ids)

    def test_fake_designplan_mapping_reference_is_repaired_or_failed(self):
        bad = base_power_draft()
        bad["implementation_mappings"][0]["design_plan_refs"] = ["BLOCK_FAKE"]
        result = CircuitPlanner(FakeLLMClient([json.dumps(bad)]), max_repair_attempts=0).plan_circuit(base_context())

        self.assertEqual(result.status, CircuitPlanningStatus.FAILED)

    def test_one_component_can_map_to_multiple_designplan_blocks(self):
        draft = base_power_draft()
        draft["component_instances"][0]["source_design_plan_refs"].append("BLOCK_PROT_001")
        draft["implementation_mappings"][0]["design_plan_refs"].append("BLOCK_PROT_001")
        result = planner_with_draft(draft).plan_circuit(base_context())

        self.assertEqual(result.status, CircuitPlanningStatus.PARTIAL)
        self.assertEqual(result.circuit_ir.components[0].source_block_ids, ["BLOCK_PWR_001", "BLOCK_PROT_001"])

    def test_proposed_candidate_with_unknown_current_does_not_resolve_canonical_component(self):
        context = base_context(records=[component(include_current=False)])
        result = planner_with_draft(base_power_draft(proposed_component_record_id="CMP_001")).plan_circuit(context)
        selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")
        evaluation = next(item for item in result.candidate_evaluations if item.component_record_id == "CMP_001")

        self.assertEqual(evaluation.eligibility, CandidateEligibility.UNKNOWN)
        self.assertIsNone(selected.component_record_id)
        self.assertNotEqual(result.status, CircuitPlanningStatus.ACCEPTED)
        self.assertTrue(any(issue.issue_type == "knowledge_missing" for issue in result.issues))

    def test_proposed_candidate_with_low_current_is_rejected_and_not_resolved(self):
        context = base_context(records=[component(max_current=1)])
        result = planner_with_draft(base_power_draft(proposed_component_record_id="CMP_001")).plan_circuit(context)
        selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")
        evaluation = next(item for item in result.candidate_evaluations if item.component_record_id == "CMP_001")

        self.assertEqual(evaluation.eligibility, CandidateEligibility.REJECTED)
        self.assertIsNone(selected.component_record_id)
        self.assertTrue(any(issue.issue_type == "no_candidate" for issue in result.issues))

    def test_aec_required_proposed_unknown_no_and_yes_are_fail_closed(self):
        for record, expected, resolved in [
            (component("CMP_UNKNOWN_AEC", aec_state="unknown"), CandidateEligibility.UNKNOWN, False),
            (component("CMP_NO_AEC", aec_state="verified_no"), CandidateEligibility.REJECTED, False),
            (component("CMP_OK_AEC", aec_state="verified"), CandidateEligibility.ELIGIBLE, True),
        ]:
            with self.subTest(record=record.component_id):
                context = base_context(
                    records=[record],
                    configuration=CircuitPlannerConfiguration(required_qualifications=("AEC_Q100",)),
                )
                result = planner_with_draft(base_power_draft(proposed_component_record_id=record.component_id)).plan_circuit(context)
                selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")
                evaluation = next(item for item in result.candidate_evaluations if item.component_record_id == record.component_id)

                self.assertEqual(evaluation.eligibility, expected)
                self.assertEqual(selected.component_record_id == record.component_id, resolved)

    def test_forced_component_duplicate_conflict_needs_input(self):
        context = base_context(
            records=[component("CMP_A"), component("CMP_B")],
            forced=(
                ForcedComponentConstraint(target_role="main_power_converter", component_record_id="CMP_A"),
                ForcedComponentConstraint(target_role="main_power_converter", component_record_id="CMP_B"),
            ),
        )
        result = planner_with_draft(base_power_draft()).plan_circuit(context)

        self.assertEqual(result.status, CircuitPlanningStatus.NEEDS_INPUT)
        self.assertTrue(any(issue.issue_type == "constraint_conflict" and issue.blocking for issue in result.issues))
        selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")
        self.assertIsNone(selected.component_record_id)

    def test_forced_incompatible_component_remains_unresolved(self):
        context = base_context(
            records=[component(max_current=1)],
            forced=(ForcedComponentConstraint(target_role="main_power_converter", component_record_id="CMP_001"),),
        )
        result = planner_with_draft(base_power_draft()).plan_circuit(context)
        selected = next(component for component in result.circuit_ir.components if component.role == "main_power_converter")

        self.assertEqual(result.status, CircuitPlanningStatus.NEEDS_INPUT)
        self.assertIsNone(selected.component_record_id)

    def test_llm_resolved_pin_claims_are_downgraded_without_pinout_knowledge(self):
        draft = fully_resolved_draft()
        for pin in draft["component_instances"][0]["pin_drafts"]:
            pin["pin_number"] = "999"
            pin["resolution_status"] = "resolved"
        result = planner_with_draft(draft).plan_circuit(base_context())

        pins = result.circuit_ir.components[0].pins
        self.assertTrue(all(pin.pin_number is None for pin in pins))
        self.assertTrue(all(pin.resolution_status == "unresolved" for pin in pins))
        self.assertNotEqual(result.status, CircuitPlanningStatus.ACCEPTED)

    def test_llm_invented_values_and_parameters_are_not_copied(self):
        draft = base_power_draft()
        draft["component_instances"][1]["value"] = {"kind": "quantity", "quantity": {"value": 22, "unit": "uF"}}
        draft["component_instances"][1]["parameters"] = [
            {"name": "switching_frequency", "value": {"kind": "quantity", "quantity": {"value": 500, "unit": "kHz"}}, "source": "llm"}
        ]
        result = planner_with_draft(draft).plan_circuit(base_context())
        input_cap = next(component for component in result.circuit_ir.components if component.role == "input_decoupling")

        self.assertIsNone(input_cap.value)
        self.assertEqual(input_cap.parameters, [])

    def test_evidence_backed_component_value_is_canonical_with_basis(self):
        draft = base_power_draft()
        draft["component_instances"][1]["proposed_component_record_id"] = "CMP_CAP_001"
        context = base_context(records=[component(), passive_component()])
        result = planner_with_draft(draft).plan_circuit(context)
        input_cap = next(component for component in result.circuit_ir.components if component.role == "input_decoupling")
        evaluation = next(item for item in result.candidate_evaluations if item.component_record_id == "CMP_CAP_001")

        self.assertEqual(input_cap.component_record_id, "CMP_CAP_001")
        self.assertEqual(input_cap.value.quantity.value, 22)
        self.assertEqual(input_cap.value.quantity.unit, "uF")
        self.assertEqual(evaluation.value_resolution_bases[0].component_attribute_ids, ["ATTR_CMP_CAP_001_VALUE"])
        self.assertEqual(evaluation.value_resolution_bases[0].evidence_ids, ["EVID_DS_001"])

    def test_semantic_ids_are_independent_of_draft_component_order(self):
        draft_a = base_power_draft()
        draft_b = copy.deepcopy(draft_a)
        draft_b["component_instances"] = list(reversed(draft_b["component_instances"]))
        draft_b["nets"] = list(reversed(draft_b["nets"]))

        result_a = planner_with_draft(draft_a).plan_circuit(base_context())
        result_b = planner_with_draft(draft_b).plan_circuit(base_context())
        ids_a = {component.role: component.instance_id for component in result_a.circuit_ir.components}
        ids_b = {component.role: component.instance_id for component in result_b.circuit_ir.components}
        nets_a = {net.name: net.net_id for net in result_a.circuit_ir.nets}
        nets_b = {net.name: net.net_id for net in result_b.circuit_ir.nets}

        self.assertEqual(ids_a, ids_b)
        self.assertEqual(nets_a, nets_b)

    def test_refinement_preserves_all_continuing_refdes(self):
        first = planner_with_draft(base_power_draft()).plan_circuit(base_context(records=[])).circuit_ir
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context(existing=first))

        self.assertEqual(
            {component.instance_id: component.reference_designator for component in result.circuit_ir.components},
            {component.instance_id: component.reference_designator for component in first.components},
        )

    def test_candidate_selection_is_independent_of_knowledge_context_order(self):
        draft = base_power_draft()
        result_a = planner_with_draft(draft).plan_circuit(base_context(records=[component("CMP_B"), component("CMP_A")]))
        result_b = planner_with_draft(draft).plan_circuit(base_context(records=[component("CMP_A"), component("CMP_B")]))
        selected_a = next(component for component in result_a.circuit_ir.components if component.role == "main_power_converter")
        selected_b = next(component for component in result_b.circuit_ir.components if component.role == "main_power_converter")

        self.assertEqual(selected_a.component_record_id, "CMP_A")
        self.assertEqual(selected_b.component_record_id, "CMP_A")

    def test_result_contract_rejects_invalid_status_combinations(self):
        partial_circuit = planner_with_draft(base_power_draft()).plan_circuit(base_context()).circuit_ir
        resolved_circuit = artificial_resolved_circuit()
        blocking_issue = CircuitPlanningIssue(
            issue_id="CPI_BLOCKING",
            issue_type="knowledge_missing",
            target_ids=[],
            description="Missing decision.",
            blocking=True,
        )

        invalid_cases = [
            {"status": "accepted"},
            {"status": "partial"},
            {"status": "accepted", "circuit_ir": partial_circuit},
            {"status": "failed", "circuit_ir": partial_circuit},
            {"status": "needs_input", "issues": []},
        ]
        for data in invalid_cases:
            with self.subTest(status=data["status"]):
                with self.assertRaises(ValidationError):
                    CircuitPlanningResult.model_validate(data)

        self.assertTrue(CircuitPlanningResult(status="accepted", circuit_ir=resolved_circuit).accepted)
        self.assertEqual(CircuitPlanningResult(status="partial", circuit_ir=partial_circuit).status, CircuitPlanningStatus.PARTIAL)
        self.assertEqual(
            CircuitPlanningResult(status="needs_input", circuit_ir=partial_circuit, issues=[blocking_issue]).status,
            CircuitPlanningStatus.NEEDS_INPUT,
        )

    def test_incompatible_existing_circuit_lineage_needs_input_without_borrowing_identity(self):
        existing = planner_with_draft(base_power_draft()).plan_circuit(base_context()).circuit_ir
        data = existing.model_dump(mode="json")
        data["circuit_id"] = "CIR_FOREIGN"
        data["project_id"] = "PRJ_FOREIGN"
        data["source_design_plan"]["design_plan_id"] = "DPLAN_FOREIGN"
        foreign = CircuitIR.model_validate(data)
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context(existing=foreign))

        self.assertEqual(result.status, CircuitPlanningStatus.NEEDS_INPUT)
        self.assertIsNone(result.circuit_ir)
        self.assertTrue(any(issue.blocking for issue in result.issues))

    def test_designplan_omission_is_explicit_partial_issue(self):
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context())

        self.assertEqual(result.status, CircuitPlanningStatus.PARTIAL)
        omitted_ids = {target for issue in result.issues if issue.issue_type == "incomplete_architecture" for target in issue.target_ids}
        self.assertIn("BLOCK_SENSOR_001", omitted_ids)
        self.assertIn("IF_I2C_001", omitted_ids)

    def test_refdes_are_independent_of_draft_component_order(self):
        draft_a = base_power_draft()
        draft_b = copy.deepcopy(draft_a)
        draft_b["component_instances"] = list(reversed(draft_b["component_instances"]))

        result_a = planner_with_draft(draft_a).plan_circuit(base_context())
        result_b = planner_with_draft(draft_b).plan_circuit(base_context())
        refdes_a = {component.role: component.reference_designator for component in result_a.circuit_ir.components}
        refdes_b = {component.role: component.reference_designator for component in result_b.circuit_ir.components}

        self.assertEqual(refdes_a["input_decoupling"], "C1")
        self.assertEqual(refdes_a["output_decoupling"], "C2")
        self.assertEqual(refdes_a, refdes_b)

    def test_assumption_ids_are_independent_of_draft_order(self):
        draft_a = base_power_draft()
        draft_a["assumptions"] = [
            {"statement": "Input capacitor value pending evidence.", "target_draft_refs": ["input_cap"], "source": "planner"},
            {"statement": "Inductor value pending evidence.", "target_draft_refs": ["inductor"], "source": "planner"},
        ]
        draft_b = copy.deepcopy(draft_a)
        draft_b["assumptions"] = list(reversed(draft_b["assumptions"]))

        result_a = planner_with_draft(draft_a).plan_circuit(base_context())
        result_b = planner_with_draft(draft_b).plan_circuit(base_context())
        assumptions_a = {assumption.statement: assumption.assumption_id for assumption in result_a.circuit_ir.assumptions}
        assumptions_b = {assumption.statement: assumption.assumption_id for assumption in result_b.circuit_ir.assumptions}

        self.assertEqual(assumptions_a, assumptions_b)

    def test_open_decision_ids_are_independent_of_draft_order(self):
        draft_a = base_power_draft()
        draft_a["open_decisions"] = [
            {
                "topic": "input_decoupling_value",
                "description": "Choose input capacitor value.",
                "target_draft_refs": ["input_cap"],
                "blocking": False,
                "driven_by_design_plan_refs": ["BLOCK_PWR_001"],
            },
            {
                "topic": "inductor_value",
                "description": "Choose inductor value.",
                "target_draft_refs": ["inductor"],
                "blocking": False,
                "driven_by_design_plan_refs": ["BLOCK_PWR_001"],
            },
        ]
        draft_b = copy.deepcopy(draft_a)
        draft_b["open_decisions"] = list(reversed(draft_b["open_decisions"]))

        result_a = planner_with_draft(draft_a).plan_circuit(base_context())
        result_b = planner_with_draft(draft_b).plan_circuit(base_context())
        decisions_a = {decision.topic: decision.decision_id for decision in result_a.circuit_ir.open_decisions}
        decisions_b = {decision.topic: decision.decision_id for decision in result_b.circuit_ir.open_decisions}

        self.assertEqual(decisions_a, decisions_b)

    def test_interface_binding_ids_are_independent_of_draft_order(self):
        draft_a = {
            "component_instances": [
                support_component("pullup_sda", "i2c_sda_pullup", "resistor", ["sda", "vcc"]),
                support_component("pullup_scl", "i2c_scl_pullup", "resistor", ["scl", "vcc"]),
            ],
            "nets": [
                {
                    "draft_net_id": "sda",
                    "name_hint": "SDA",
                    "role": "communication",
                    "connections": [{"component_draft_id": "pullup_sda", "draft_pin_id": "pullup_sda_pin_a"}],
                },
                {
                    "draft_net_id": "scl",
                    "name_hint": "SCL",
                    "role": "communication",
                    "connections": [{"component_draft_id": "pullup_scl", "draft_pin_id": "pullup_scl_pin_a"}],
                },
                {
                    "draft_net_id": "vcc",
                    "name_hint": "5V",
                    "role": "power",
                    "power_domain_ref": "PWRDOM_5V",
                    "connections": [
                        {"component_draft_id": "pullup_sda", "draft_pin_id": "pullup_sda_pin_b"},
                        {"component_draft_id": "pullup_scl", "draft_pin_id": "pullup_scl_pin_b"},
                    ],
                },
            ],
            "implementation_mappings": [
                {
                    "draft_mapping_id": "map_i2c",
                    "design_plan_refs": ["IF_I2C_001"],
                    "circuit_draft_refs": ["pullup_sda", "pullup_scl", "sda", "scl"],
                    "mapping_type": "interfaces",
                    "status": "partial",
                }
            ],
        }
        draft_b = copy.deepcopy(draft_a)
        draft_b["component_instances"] = list(reversed(draft_b["component_instances"]))
        draft_b["nets"] = list(reversed(draft_b["nets"]))

        result_a = planner_with_draft(draft_a).plan_circuit(base_context())
        result_b = planner_with_draft(draft_b).plan_circuit(base_context())

        self.assertEqual(
            {binding.design_plan_interface_id: binding.binding_id for binding in result_a.circuit_ir.interface_bindings},
            {binding.design_plan_interface_id: binding.binding_id for binding in result_b.circuit_ir.interface_bindings},
        )

    def test_group_ids_are_independent_of_draft_order(self):
        draft_a = base_power_draft()
        draft_b = copy.deepcopy(draft_a)
        draft_b["component_instances"] = list(reversed(draft_b["component_instances"]))
        draft_b["nets"] = list(reversed(draft_b["nets"]))

        result_a = planner_with_draft(draft_a).plan_circuit(base_context())
        result_b = planner_with_draft(draft_b).plan_circuit(base_context())

        self.assertEqual(result_a.circuit_ir.groups[0].group_id, result_b.circuit_ir.groups[0].group_id)
        self.assertEqual(result_a.circuit_ir.groups[0].source_block_ids, result_b.circuit_ir.groups[0].source_block_ids)

    def test_mapping_ids_are_independent_of_endpoint_order(self):
        draft_a = base_power_draft()
        draft_a["implementation_mappings"] = [
            {
                "draft_mapping_id": "map_power",
                "design_plan_refs": ["BLOCK_PWR_001", "PWRDOM_5V"],
                "circuit_draft_refs": ["TPS54331", "input_cap", "NET_5V", "GPIO21"],
                "mapping_type": "implements",
                "status": "partial",
            },
            {
                "draft_mapping_id": "map_support",
                "design_plan_refs": ["BLOCK_PWR_001"],
                "circuit_draft_refs": ["output_cap", "inductor", "gnd"],
                "mapping_type": "supports",
                "status": "partial",
            },
        ]
        draft_b = copy.deepcopy(draft_a)
        draft_b["implementation_mappings"] = list(reversed(draft_b["implementation_mappings"]))
        for mapping in draft_b["implementation_mappings"]:
            mapping["design_plan_refs"] = list(reversed(mapping["design_plan_refs"]))
            mapping["circuit_draft_refs"] = list(reversed(mapping["circuit_draft_refs"]))

        result_a = planner_with_draft(draft_a).plan_circuit(base_context())
        result_b = planner_with_draft(draft_b).plan_circuit(base_context())
        mappings_a = {
            (tuple(sorted(mapping.design_plan_object_ids)), tuple(sorted(mapping.circuit_object_ids)), mapping.mapping_type): mapping.mapping_id
            for mapping in result_a.circuit_ir.implementation_mappings
        }
        mappings_b = {
            (tuple(sorted(mapping.design_plan_object_ids)), tuple(sorted(mapping.circuit_object_ids)), mapping.mapping_type): mapping.mapping_id
            for mapping in result_b.circuit_ir.implementation_mappings
        }

        self.assertEqual(mappings_a, mappings_b)

    def test_partial_result_rejects_resolved_circuit_even_with_nonblocking_issues(self):
        resolved_circuit = artificial_resolved_circuit()
        issue = CircuitPlanningIssue(
            issue_id="CPI_WARNING",
            issue_type="implementation_ambiguity",
            target_ids=[],
            description="Non-blocking note.",
            blocking=False,
        )

        for issues in ([issue], [issue, copy.deepcopy(issue).model_copy(update={"issue_id": "CPI_WARNING_2"})]):
            with self.subTest(issue_count=len(issues)):
                with self.assertRaises(ValidationError):
                    CircuitPlanningResult(status="partial", circuit_ir=resolved_circuit, issues=issues)

    def test_valid_result_combinations_remain_valid(self):
        partial_circuit = planner_with_draft(base_power_draft()).plan_circuit(base_context()).circuit_ir
        resolved_circuit = artificial_resolved_circuit()
        blocking_issue = CircuitPlanningIssue(
            issue_id="CPI_BLOCKING_VALID",
            issue_type="knowledge_missing",
            target_ids=[],
            description="Need user input.",
            blocking=True,
        )

        self.assertTrue(CircuitPlanningResult(status="accepted", circuit_ir=resolved_circuit).accepted)
        self.assertEqual(CircuitPlanningResult(status="partial", circuit_ir=partial_circuit).status, CircuitPlanningStatus.PARTIAL)
        self.assertEqual(
            CircuitPlanningResult(status="needs_input", circuit_ir=partial_circuit, issues=[blocking_issue]).status,
            CircuitPlanningStatus.NEEDS_INPUT,
        )
        self.assertEqual(CircuitPlanningResult(status="failed").status, CircuitPlanningStatus.FAILED)

    def test_existing_circuit_designplan_revision_mismatch_needs_input(self):
        existing = planner_with_draft(base_power_draft()).plan_circuit(base_context()).circuit_ir
        data = existing.model_dump(mode="json")
        data["source_design_plan"]["revision"] = 999
        stale = CircuitIR.model_validate(data)
        result = planner_with_draft(base_power_draft()).plan_circuit(base_context(existing=stale))

        self.assertEqual(result.status, CircuitPlanningStatus.NEEDS_INPUT)
        self.assertIsNone(result.circuit_ir)
        self.assertTrue(any("revision" in issue.description for issue in result.issues))

    def test_soft_designplan_omission_is_visible_and_nonblocking(self):
        requirements = requirement_model()
        plan_data = design_plan().model_dump(mode="json")
        plan_data["functional_blocks"].append(
            {
                "block_id": "BLOCK_LED_001",
                "type": "user_interface",
                "name": "Status LED",
                "purpose": "Expose optional status indication.",
                "topology_class": None,
                "inputs": [],
                "outputs": [],
                "status": "planned",
            }
        )
        plan_data["interfaces"].append(
            {
                "interface_id": "IF_STATUS_001",
                "type": "gpio",
                "name": "Status Interface",
                "participants": ["BLOCK_LED_001"],
                "direction": "output",
                "power_domain": None,
            }
        )
        plan_data["power_domains"].append(
            {
                "power_domain_id": "PWRDOM_LED_001",
                "name": "Optional LED Supply",
                "role": "logic_supply",
                "voltage": None,
                "source_block": None,
                "consumer_blocks": ["BLOCK_LED_001"],
            }
        )
        plan_data["requirement_mappings"].append(
            {
                "mapping_id": "MAP_LED_001",
                "requirement_id": "REQ_PREF_001",
                "implemented_by": [
                    {"type": "functional_block", "id": "BLOCK_LED_001"},
                    {"type": "interface", "id": "IF_STATUS_001"},
                    {"type": "power_domain", "id": "PWRDOM_LED_001"},
                ],
                "status": "mapped",
            }
        )
        plan = DesignPlan.model_validate(plan_data)
        result = planner_with_draft(fully_scoped_power_draft()).plan_circuit(context_with_models(requirements, plan))

        omissions = {issue.target_ids[0]: issue for issue in result.issues if issue.issue_type == "incomplete_architecture"}
        self.assertIn("BLOCK_LED_001", omissions)
        self.assertIn("IF_STATUS_001", omissions)
        self.assertIn("PWRDOM_LED_001", omissions)
        self.assertFalse(omissions["BLOCK_LED_001"].blocking)
        self.assertFalse(omissions["IF_STATUS_001"].blocking)
        self.assertFalse(omissions["PWRDOM_LED_001"].blocking)

    def test_full_designplan_scope_has_no_incomplete_architecture_issues(self):
        result = planner_with_draft(fully_scoped_power_draft()).plan_circuit(base_context())

        self.assertFalse(any(issue.issue_type == "incomplete_architecture" for issue in result.issues))

    def test_assumptions_same_source_targets_different_topics_get_distinct_stable_ids(self):
        draft = base_power_draft()
        draft["assumptions"] = [
            {
                "semantic_topic": "grounding",
                "statement": "Ground return is assumed common for the power skeleton.",
                "target_draft_refs": ["input_cap"],
                "source": "planner",
            },
            {
                "semantic_topic": "connectivity",
                "statement": "Input capacitor connectivity is assumed pending pinout evidence.",
                "target_draft_refs": ["input_cap"],
                "source": "planner",
            },
        ]
        result = planner_with_draft(draft).plan_circuit(base_context())
        ids = {assumption.source + ":" + assumption.statement: assumption.assumption_id for assumption in result.circuit_ir.assumptions}

        self.assertEqual(len(set(ids.values())), 2)
        self.assertTrue(all(assumption_id.startswith("CIASM_") for assumption_id in ids.values()))

    def test_assumption_rewording_preserves_topic_based_ids_across_refinement(self):
        draft_v1 = base_power_draft()
        draft_v1["assumptions"] = [
            {
                "semantic_topic": "grounding",
                "statement": "Alpha grounding statement.",
                "target_draft_refs": ["input_cap"],
                "source": "planner",
            },
            {
                "semantic_topic": "connectivity",
                "statement": "Beta connectivity statement.",
                "target_draft_refs": ["input_cap"],
                "source": "planner",
            },
        ]
        first = planner_with_draft(draft_v1).plan_circuit(base_context()).circuit_ir
        first_snapshot = first.model_dump(mode="json")
        draft_v2 = copy.deepcopy(draft_v1)
        draft_v2["assumptions"] = [
            {
                "semantic_topic": "grounding",
                "statement": "Zulu grounding statement.",
                "target_draft_refs": ["input_cap"],
                "source": "planner",
            },
            {
                "semantic_topic": "connectivity",
                "statement": "Able connectivity statement.",
                "target_draft_refs": ["input_cap"],
                "source": "planner",
            },
        ]

        refined = planner_with_draft(draft_v2).plan_circuit(base_context(existing=first)).circuit_ir
        ids_v1 = {assumption.assumption_id for assumption in first.assumptions}
        ids_v2 = {assumption.assumption_id for assumption in refined.assumptions}

        self.assertEqual(ids_v1, ids_v2)
        self.assertEqual(first.model_dump(mode="json"), first_snapshot)

    def test_duplicate_assumption_semantic_key_is_rejected(self):
        draft = base_power_draft()
        draft["assumptions"] = [
            {
                "semantic_topic": "grounding",
                "statement": "First wording.",
                "target_draft_refs": ["input_cap"],
                "source": "planner",
            },
            {
                "semantic_topic": "grounding",
                "statement": "Different wording.",
                "target_draft_refs": ["input_cap"],
                "source": "planner",
            },
        ]

        with self.assertRaises(ValidationError):
            CircuitIRDraft.model_validate(draft)

    def test_open_decision_does_not_mask_block_omission(self):
        draft = base_power_draft()
        draft["open_decisions"] = [
            {
                "topic": "input_stage_unresolved",
                "description": "Input stage still needs implementation.",
                "target_draft_refs": [],
                "blocking": False,
                "driven_by_design_plan_refs": ["BLOCK_INPUT_001"],
            }
        ]
        result = planner_with_draft(draft).plan_circuit(base_context())
        omitted_ids = {target for issue in result.issues if issue.issue_type == "incomplete_architecture" for target in issue.target_ids}

        self.assertIn("BLOCK_INPUT_001", omitted_ids)
        self.assertTrue(any(decision.topic == "input_stage_unresolved" for decision in result.circuit_ir.open_decisions))

    def test_open_decision_with_actual_block_implementation_does_not_create_false_omission(self):
        draft = base_power_draft()
        input_component = support_component("input_connector", "input_entry", "connector", ["vin_raw", "vin_protected"])
        input_component["source_design_plan_refs"] = ["BLOCK_INPUT_001"]
        draft["component_instances"].append(input_component)
        draft["nets"].append(
            {
                "draft_net_id": "vin_raw",
                "name_hint": "12V",
                "role": "power",
                "power_domain_ref": "PWRDOM_VIN_RAW",
                "connections": [{"component_draft_id": "input_connector", "draft_pin_id": "input_connector_pin_a"}],
            }
        )
        draft["nets"][0]["connections"].append(
            {"component_draft_id": "input_connector", "draft_pin_id": "input_connector_pin_b"}
        )
        draft["implementation_mappings"].append(
            {
                "draft_mapping_id": "map_input",
                "design_plan_refs": ["BLOCK_INPUT_001", "PWRDOM_VIN_RAW"],
                "circuit_draft_refs": ["input_connector", "vin_raw"],
                "mapping_type": "implements",
                "status": "partial",
            }
        )
        draft["open_decisions"] = [
            {
                "topic": "input_connector_package",
                "description": "Connector package remains open.",
                "target_draft_refs": ["input_connector"],
                "blocking": False,
                "driven_by_design_plan_refs": ["BLOCK_INPUT_001"],
            }
        ]

        result = planner_with_draft(draft).plan_circuit(base_context())
        omitted_ids = {target for issue in result.issues if issue.issue_type == "incomplete_architecture" for target in issue.target_ids}

        self.assertNotIn("BLOCK_INPUT_001", omitted_ids)
        self.assertNotIn("PWRDOM_VIN_RAW", omitted_ids)
        self.assertTrue(any(decision.topic == "input_connector_package" for decision in result.circuit_ir.open_decisions))

    def test_soft_block_open_decision_does_not_mask_nonblocking_omission(self):
        requirements = requirement_model()
        plan_data = design_plan().model_dump(mode="json")
        plan_data["functional_blocks"].append(
            {
                "block_id": "BLOCK_LED_001",
                "type": "user_interface",
                "name": "Status LED",
                "purpose": "Expose optional status indication.",
                "topology_class": None,
                "inputs": [],
                "outputs": [],
                "status": "planned",
            }
        )
        plan_data["requirement_mappings"].append(
            {
                "mapping_id": "MAP_LED_001",
                "requirement_id": "REQ_PREF_001",
                "implemented_by": [{"type": "functional_block", "id": "BLOCK_LED_001"}],
                "status": "mapped",
            }
        )
        draft = fully_scoped_power_draft()
        draft["open_decisions"] = [
            {
                "topic": "status_led_deferred",
                "description": "Status LED implementation deferred.",
                "target_draft_refs": [],
                "blocking": False,
                "driven_by_design_plan_refs": ["BLOCK_LED_001"],
            }
        ]
        result = planner_with_draft(draft).plan_circuit(
            context_with_models(requirements, DesignPlan.model_validate(plan_data))
        )
        omissions = {issue.target_ids[0]: issue for issue in result.issues if issue.issue_type == "incomplete_architecture"}

        self.assertIn("BLOCK_LED_001", omissions)
        self.assertFalse(omissions["BLOCK_LED_001"].blocking)

    def test_open_decision_does_not_mask_interface_or_power_domain_omission(self):
        draft = base_power_draft()
        draft["open_decisions"] = [
            {
                "topic": "i2c_and_input_power_deferred",
                "description": "I2C and raw input power implementation deferred.",
                "target_draft_refs": [],
                "blocking": False,
                "driven_by_design_plan_refs": ["IF_I2C_001", "PWRDOM_VIN_RAW"],
            }
        ]
        result = planner_with_draft(draft).plan_circuit(base_context())
        omitted_ids = {target for issue in result.issues if issue.issue_type == "incomplete_architecture" for target in issue.target_ids}

        self.assertIn("IF_I2C_001", omitted_ids)
        self.assertIn("PWRDOM_VIN_RAW", omitted_ids)


if __name__ == "__main__":
    unittest.main()
