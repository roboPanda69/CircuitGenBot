import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from schematic_ai.application.architecture import ArchitecturePlanner, DesignPlanDraft
from schematic_ai.application.architecture.result import PlanningIssueReason, PlanningResultStatus
from schematic_ai.domain.design_plan.enums import ArchitectureChoice
from schematic_ai.domain.requirements.models import RequirementModel


ROOT = Path(__file__).resolve().parents[2]
REQUIREMENT_MODEL_PATH = ROOT / "examples" / "requirement_model_v0_1.json"
PLANNED_AT = datetime(2026, 8, 16, tzinfo=timezone.utc)


class FakeLLMClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []
        self.schemas = []

    def generate_structured(self, *, prompt, json_schema=None):
        self.prompts.append(prompt)
        self.schemas.append(json_schema)
        if not self.outputs:
            raise AssertionError("fake LLM has no more outputs")
        return self.outputs.pop(0)


def output(value):
    return json.dumps(value)


def requirement_model_data():
    return json.loads(REQUIREMENT_MODEL_PATH.read_text(encoding="utf-8"))


def requirement_model(*, with_blocking_question=False):
    data = requirement_model_data()
    if not with_blocking_question:
        data["open_questions"] = []
    return RequirementModel.model_validate(data)


def active_hard_ids(model):
    return {
        requirement.id
        for requirement in [*model.requirements, *model.derived_requirements]
        if requirement.enforcement == "hard"
        and requirement.status not in {"rejected", "superseded"}
    }


def valid_power_sensor_draft(*, open_decisions=None):
    return {
        "blocks": [
            {
                "draft_id": "b_input",
                "type": "power_input",
                "name": "Input Power Interface",
                "purpose": "Accept nominal 12 V input power from the external source.",
                "ports": [
                    {
                        "draft_id": "raw_in",
                        "name": "raw_input_power",
                        "kind": "power",
                        "direction": "input",
                        "power_domain_ref": "vin_raw",
                    },
                    {
                        "draft_id": "raw_out",
                        "name": "raw_input_power_out",
                        "kind": "power",
                        "direction": "output",
                        "power_domain_ref": "vin_raw",
                    },
                ],
            },
            {
                "draft_id": "b_protection",
                "type": "power_protection",
                "name": "Reverse Polarity Protection",
                "purpose": "Protect downstream power conversion from reversed input polarity.",
                "topology_class": "non_isolated_power_conversion",
                "ports": [
                    {
                        "draft_id": "protected_in",
                        "name": "raw_input_power",
                        "kind": "power",
                        "direction": "input",
                        "power_domain_ref": "vin_raw",
                    },
                    {
                        "draft_id": "protected_out",
                        "name": "protected_input_power",
                        "kind": "power",
                        "direction": "output",
                        "power_domain_ref": "vin_protected",
                    },
                ],
            },
            {
                "draft_id": "b_converter",
                "type": "power_conversion",
                "name": "Main 5 V Power Conversion",
                "purpose": "Convert protected input power to the regulated output rail.",
                "topology_class": "switching_step_down",
                "ports": [
                    {
                        "draft_id": "converter_in",
                        "name": "protected_input_power",
                        "kind": "power",
                        "direction": "input",
                        "power_domain_ref": "vin_protected",
                    },
                    {
                        "draft_id": "converter_out",
                        "name": "regulated_output_power",
                        "kind": "power",
                        "direction": "output",
                        "power_domain_ref": "vout_main",
                    },
                ],
            },
            {
                "draft_id": "b_sensor",
                "type": "sensor",
                "name": "Temperature Sensing",
                "purpose": "Provide temperature sensing over the logical I2C interface.",
                "topology_class": "direct_interface",
                "ports": [
                    {
                        "draft_id": "sensor_power",
                        "name": "sensor_power",
                        "kind": "power",
                        "direction": "input",
                        "power_domain_ref": "vout_main",
                    },
                    {
                        "draft_id": "sensor_i2c",
                        "name": "sensor_bus",
                        "kind": "communication",
                        "direction": "bidirectional",
                        "power_domain_ref": "vout_main",
                        "interface_ref": "i2c_bus",
                    },
                ],
            },
            {
                "draft_id": "b_host_if",
                "type": "communication",
                "name": "Host I2C Interface",
                "purpose": "Expose the temperature sensor bus to a host connection.",
                "topology_class": "direct_interface",
                "ports": [
                    {
                        "draft_id": "host_i2c",
                        "name": "host_sensor_bus",
                        "kind": "communication",
                        "direction": "bidirectional",
                        "power_domain_ref": "vout_main",
                        "interface_ref": "i2c_bus",
                    },
                ],
            },
        ],
        "connections": [
            {
                "draft_id": "c_input_to_protection",
                "source_block": "b_input",
                "source_port": "raw_out",
                "target_block": "b_protection",
                "target_port": "protected_in",
                "kind": "power",
                "description": "Raw input power feeds the reverse-polarity protection stage.",
            },
            {
                "draft_id": "c_protection_to_converter",
                "source_block": "b_protection",
                "source_port": "protected_out",
                "target_block": "b_converter",
                "target_port": "converter_in",
                "kind": "power",
                "description": "Protected input power feeds the conversion block.",
            },
            {
                "draft_id": "c_converter_to_sensor",
                "source_block": "b_converter",
                "source_port": "converter_out",
                "target_block": "b_sensor",
                "target_port": "sensor_power",
                "kind": "power",
                "description": "The regulated output rail powers the temperature sensing block.",
            },
            {
                "draft_id": "c_i2c_bus",
                "source_block": "b_sensor",
                "source_port": "sensor_i2c",
                "target_block": "b_host_if",
                "target_port": "host_i2c",
                "kind": "communication",
                "description": "Logical bidirectional I2C communication between sensor and host interface.",
            },
        ],
        "power_domains": [
            {
                "draft_id": "vin_raw",
                "name": "Raw Input Power",
                "role": "input",
                "voltage": {"kind": "nominal", "value": 12, "unit": "V"},
                "source_block": "b_input",
                "consumer_blocks": ["b_protection"],
            },
            {
                "draft_id": "vin_protected",
                "name": "Protected Input Power",
                "role": "protected_input",
                "voltage": {"kind": "nominal", "value": 12, "unit": "V"},
                "source_block": "b_protection",
                "consumer_blocks": ["b_converter"],
            },
            {
                "draft_id": "vout_main",
                "name": "Regulated Output Rail",
                "role": "regulated_output",
                "voltage": {"kind": "nominal", "value": 5, "unit": "V"},
                "source_block": "b_converter",
                "consumer_blocks": ["b_sensor", "b_host_if"],
            },
        ],
        "interfaces": [
            {
                "draft_id": "i2c_bus",
                "type": "i2c",
                "name": "Temperature Sensor Bus",
                "participants": ["b_sensor", "b_host_if"],
                "direction": "bidirectional",
                "power_domain_ref": "vout_main",
            }
        ],
        "requirement_mappings": [
            {
                "requirement_id": "REQ_PWR_001",
                "targets": [
                    {"type": "functional_block", "draft_id": "b_input"},
                    {"type": "power_domain", "draft_id": "vin_raw"},
                ],
                "status": "mapped",
            },
            {
                "requirement_id": "REQ_PROT_001",
                "targets": [{"type": "functional_block", "draft_id": "b_protection"}],
                "status": "mapped",
            },
            {
                "requirement_id": "REQ_PWR_002",
                "targets": [
                    {"type": "functional_block", "draft_id": "b_converter"},
                    {"type": "power_domain", "draft_id": "vout_main"},
                ],
                "status": "mapped",
            },
            {
                "requirement_id": "REQ_PWR_003",
                "targets": [
                    {"type": "functional_block", "draft_id": "b_converter"},
                    {"type": "power_domain", "draft_id": "vout_main"},
                ],
                "status": "mapped",
            },
            {
                "requirement_id": "REQ_IF_001",
                "targets": [
                    {"type": "functional_block", "draft_id": "b_sensor"},
                    {"type": "interface", "draft_id": "i2c_bus"},
                ],
                "status": "mapped",
            },
            {
                "requirement_id": "DREQ_IF_001",
                "targets": [],
                "status": "unresolved",
            },
        ],
        "architecture_decisions": [
            {
                "draft_id": "d_power_topology",
                "type": "topology_choice",
                "target": {"type": "functional_block", "draft_id": "b_converter"},
                "choice": "switching_step_down",
                "rationale": "A step-down topology matches the higher input voltage and lower regulated output rail.",
                "driven_by_requirements": ["REQ_PWR_001", "REQ_PWR_002", "REQ_PWR_003"],
                "status": "accepted",
            },
            {
                "draft_id": "d_i2c_strategy",
                "type": "interface_strategy",
                "target": {"type": "interface", "draft_id": "i2c_bus"},
                "choice": "direct_interface",
                "rationale": "The requirement explicitly calls for an I2C interface.",
                "driven_by_requirements": ["REQ_IF_001"],
                "status": "accepted",
            },
        ],
        "assumptions": [
            {
                "description": "All low-voltage functional blocks share a common ground domain.",
                "impact": "medium",
                "affected_blocks": ["b_converter", "b_sensor", "b_host_if"],
            }
        ],
        "open_decisions": open_decisions
        if open_decisions is not None
        else [
            {
                "topic": "host_interface_strategy",
                "description": "The architecture has not yet selected how the sensor interface is physically exposed.",
                "options": ["direct_interface", "interface_bridge"],
                "blocking": False,
                "affected_blocks": ["b_sensor", "b_host_if"],
            }
        ],
    }


def replace_draft_refs(value, replacements):
    if isinstance(value, dict):
        return {key: replace_draft_refs(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_draft_refs(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def hostile_temp_id_draft():
    replacements = {
        "b_input": "TPS54331",
        "b_protection": "LM2596",
        "b_converter": "GPIO21",
        "b_sensor": "NET_5V",
        "b_host_if": "Package_SO_SOIC8",
        "raw_in": "R1",
        "raw_out": "C1",
        "protected_in": "L1",
        "protected_out": "TPS62160",
        "converter_in": "random_name",
        "converter_out": "foo",
        "sensor_power": "bar",
        "sensor_i2c": "baz",
        "host_i2c": "mpn_like",
        "vin_raw": "R1",
        "vin_protected": "C1",
        "vout_main": "L1",
        "i2c_bus": "TPS62160",
        "c_input_to_protection": "NET_5V",
        "c_protection_to_converter": "GPIO21",
        "c_converter_to_sensor": "TPS54331",
        "c_i2c_bus": "LM2596",
        "d_power_topology": "Package_SO_SOIC8",
        "d_i2c_strategy": "R1",
    }
    return replace_draft_refs(valid_power_sensor_draft(), replacements)


def implementation_prose_draft():
    draft = valid_power_sensor_draft()
    draft["blocks"][2]["name"] = "TPS54331 Buck Converter"
    draft["blocks"][2]["purpose"] = "Use L1 = 10uH and C1 = 22uF around the selected IC."
    draft["connections"][1]["description"] = "Route NET_5V to the LM2596 buck stage."
    draft["power_domains"][2]["name"] = "TPS54331 output rail"
    draft["interfaces"][0]["name"] = "GPIO21 I2C pins"
    draft["architecture_decisions"][0]["rationale"] = "LM2596 should be used because it is common."
    draft["assumptions"][0]["description"] = "C1 = 22uF is assumed."
    draft["open_decisions"][0]["topic"] = "TPS54331_or_LM2596"
    draft["open_decisions"][0]["description"] = "Choose between TPS54331 and LM2596."
    return draft


def set_output_domain_voltage(draft, value):
    updated = copy.deepcopy(draft)
    updated["power_domains"][2]["voltage"]["value"] = value
    return updated


def set_interface_type(draft, interface_type):
    updated = copy.deepcopy(draft)
    updated["interfaces"][0]["type"] = interface_type
    return updated


class DesignPlanDraftTests(unittest.TestCase):
    def test_duplicate_and_dangling_draft_refs_are_rejected(self):
        duplicate = valid_power_sensor_draft()
        duplicate["blocks"][1]["draft_id"] = "b_input"
        with self.assertRaises(ValidationError):
            DesignPlanDraft.model_validate(duplicate)

        dangling = valid_power_sensor_draft()
        dangling["connections"][0]["target_block"] = "b_missing"
        with self.assertRaises(ValidationError):
            DesignPlanDraft.model_validate(dangling)

    def test_component_specific_draft_fields_and_choices_are_rejected(self):
        extra_field = valid_power_sensor_draft()
        extra_field["blocks"][2]["component"] = "TPS54331"
        with self.assertRaises(ValidationError):
            DesignPlanDraft.model_validate(extra_field)

        component_choice = valid_power_sensor_draft()
        component_choice["architecture_decisions"][0]["choice"] = "TPS54331"
        with self.assertRaises(ValidationError):
            DesignPlanDraft.model_validate(component_choice)

        component_option = valid_power_sensor_draft()
        component_option["open_decisions"][0]["options"] = ["LM2596"]
        with self.assertRaises(ValidationError):
            DesignPlanDraft.model_validate(component_option)


class ArchitecturePlannerTests(unittest.TestCase):
    def test_initial_planning_accepts_functional_power_sensor_architecture(self):
        fake = FakeLLMClient([output(valid_power_sensor_draft())])
        result = ArchitecturePlanner(fake).plan_architecture(requirement_model(), planned_at=PLANNED_AT)

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        self.assertTrue(result.accepted)
        self.assertEqual(result.design_plan.design_plan_id, "DPLAN_0001")
        self.assertEqual(result.design_plan.source_requirement_set.requirement_set_id, "RQS_0001")
        self.assertEqual(result.design_plan.source_requirement_set.revision, 1)
        self.assertEqual(result.design_plan.metadata.created_by, "architecture_planner")
        self.assertEqual(result.design_plan.functional_blocks[2].block_id, "BLOCK_PWR_001")
        self.assertEqual(result.design_plan.functional_blocks[2].topology_class, "switching_step_down")
        self.assertEqual(result.design_plan.interfaces[0].interface_id, "IF_I2C_001")
        self.assertEqual(result.design_plan.interfaces[0].type, "i2c")
        self.assertEqual(result.design_plan.power_domains[2].power_domain_id, "PWRDOM_003")
        self.assertEqual(active_hard_ids(requirement_model()), {mapping.requirement_id for mapping in result.design_plan.requirement_mappings})
        self.assertIsInstance(result.design_plan.architecture_decisions[0].choice, ArchitectureChoice)
        self.assertEqual(len(fake.prompts), 1)
        self.assertIn("RequirementModel summary", fake.prompts[0])
        self.assertIn("Do not select components", fake.prompts[0])

    def test_reverse_protection_and_i2c_interface_are_mapped(self):
        result = ArchitecturePlanner(FakeLLMClient([output(valid_power_sensor_draft())])).plan_architecture(
            requirement_model(),
            planned_at=PLANNED_AT,
        )
        plan = result.design_plan

        protection_mapping = next(mapping for mapping in plan.requirement_mappings if mapping.requirement_id == "REQ_PROT_001")
        protection_block_id = protection_mapping.implemented_by[0].id
        protection_block = next(block for block in plan.functional_blocks if block.block_id == protection_block_id)
        self.assertEqual(protection_block.type, "power_protection")
        self.assertEqual(protection_block.name, "Reverse-Polarity Power Protection")

        interface_mapping = next(mapping for mapping in plan.requirement_mappings if mapping.requirement_id == "REQ_IF_001")
        self.assertIn("IF_I2C_001", {target.id for target in interface_mapping.implemented_by})
        self.assertEqual(plan.interfaces[0].participants, ["BLOCK_SENSOR_001", "BLOCK_COMM_001"])

    def test_canonical_ids_do_not_derive_from_hostile_temporary_draft_ids(self):
        hostile_tokens = {
            "TPS54331",
            "LM2596",
            "GPIO21",
            "NET_5V",
            "R1",
            "C1",
            "L1",
            "PACKAGE_SO_SOIC8",
        }
        result = ArchitecturePlanner(FakeLLMClient([output(hostile_temp_id_draft())])).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        plan = result.design_plan
        canonical_ids = [
            plan.design_plan_id,
            *(block.block_id for block in plan.functional_blocks),
            *(port.port_id for block in plan.functional_blocks for port in [*block.inputs, *block.outputs]),
            *(domain.power_domain_id for domain in plan.power_domains),
            *(interface.interface_id for interface in plan.interfaces),
            *(connection.connection_id for connection in plan.block_connections),
            *(mapping.mapping_id for mapping in plan.requirement_mappings),
            *(decision.decision_id for decision in plan.architecture_decisions),
            *(assumption.assumption_id for assumption in plan.assumptions),
            *(decision.open_decision_id for decision in plan.open_decisions),
        ]
        for canonical_id in canonical_ids:
            with self.subTest(canonical_id=canonical_id):
                self.assertFalse(any(token in canonical_id for token in hostile_tokens))

        self.assertEqual(plan.functional_blocks[2].block_id, "BLOCK_PWR_001")
        self.assertEqual(plan.power_domains[0].power_domain_id, "PWRDOM_001")
        self.assertEqual(plan.functional_blocks[2].inputs[0].port_id, "PORT_PWR_001")

    def test_canonical_text_is_planner_owned_not_raw_implementation_prose(self):
        result = ArchitecturePlanner(FakeLLMClient([output(implementation_prose_draft())])).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        plan = result.design_plan
        canonical_json = plan.model_dump_json()
        for forbidden in ["TPS54331", "LM2596", "L1 = 10uH", "C1 = 22uF", "GPIO21", "NET_5V"]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, canonical_json)

        self.assertEqual(plan.functional_blocks[2].name, "Step-Down Power Conversion")
        self.assertEqual(
            plan.functional_blocks[2].purpose,
            "Convert the source power domain to the required lower regulated output domain.",
        )
        self.assertEqual(plan.architecture_decisions[0].choice, "switching_step_down")
        self.assertIn("switching step down", plan.architecture_decisions[0].rationale)
        self.assertEqual(plan.interfaces[0].name, "I2C Interface")

    def test_ordinary_architecture_text_is_normalized_while_structured_meaning_remains(self):
        result = ArchitecturePlanner(FakeLLMClient([output(valid_power_sensor_draft())])).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        self.assertEqual(result.design_plan.functional_blocks[0].name, "Input Power Interface")
        self.assertEqual(result.design_plan.power_domains[2].name, "5 V Regulated Output Power Domain")
        self.assertEqual(result.design_plan.architecture_decisions[1].choice, "direct_interface")

    def test_isolation_functional_input_can_be_planned_without_components(self):
        draft = valid_power_sensor_draft(open_decisions=[])
        draft["blocks"].append(
            {
                "draft_id": "b_isolation",
                "type": "isolation",
                "name": "Galvanic Isolation Boundary",
                "purpose": "Represent an architecture-level isolation boundary for downstream implementation.",
                "topology_class": "galvanic_isolation",
                "ports": [
                    {
                        "draft_id": "iso_in",
                        "name": "primary_side",
                        "kind": "power",
                        "direction": "input",
                        "power_domain_ref": "vin_protected",
                    },
                    {
                        "draft_id": "iso_out",
                        "name": "secondary_side",
                        "kind": "power",
                        "direction": "output",
                        "power_domain_ref": "vout_main",
                    },
                ],
            }
        )
        draft["architecture_decisions"].append(
            {
                "draft_id": "d_isolation",
                "type": "isolation_strategy",
                "target": {"type": "functional_block", "draft_id": "b_isolation"},
                "choice": "galvanically_isolated",
                "rationale": "A functional isolation boundary can be captured before circuit implementation.",
                "driven_by_requirements": [],
                "status": "proposed",
            }
        )

        result = ArchitecturePlanner(FakeLLMClient([output(draft)])).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        isolation = next(block for block in result.design_plan.functional_blocks if block.type == "isolation")
        self.assertEqual(isolation.block_id, "BLOCK_ISO_001")
        self.assertEqual(isolation.topology_class, "galvanic_isolation")

    def test_blocking_requirement_question_returns_needs_input_without_llm_call(self):
        fake = FakeLLMClient([output(valid_power_sensor_draft())])
        result = ArchitecturePlanner(fake).plan_architecture(requirement_model(with_blocking_question=True))

        self.assertEqual(result.status, PlanningResultStatus.NEEDS_INPUT)
        self.assertIsNone(result.design_plan)
        self.assertEqual(result.requirement_issues[0].reason, PlanningIssueReason.REQUIREMENT)
        self.assertEqual(len(fake.prompts), 0)

    def test_no_active_hard_requirement_returns_needs_input(self):
        data = requirement_model_data()
        data["open_questions"] = []
        data["requirements"] = []
        data["derived_requirements"] = []
        data["assumptions"] = []
        data["conflicts"] = []
        model = RequirementModel.model_validate(data)

        result = ArchitecturePlanner(FakeLLMClient([])).plan_architecture(model)

        self.assertEqual(result.status, PlanningResultStatus.NEEDS_INPUT)
        self.assertEqual(result.requirement_issues[0].issue_type, "no_active_hard_requirements")
        self.assertEqual(result.requirement_issues[0].reason, PlanningIssueReason.REQUIREMENT)

    def test_nonblocking_open_architecture_decision_can_still_accept(self):
        result = ArchitecturePlanner(FakeLLMClient([output(valid_power_sensor_draft())])).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        self.assertEqual(len(result.design_plan.open_decisions), 1)
        self.assertFalse(result.design_plan.open_decisions[0].blocking)

    def test_blocking_open_architecture_decision_returns_needs_input_with_plan(self):
        draft = valid_power_sensor_draft(
            open_decisions=[
                {
                    "topic": "power_topology_confirmation",
                    "description": "Select the power conversion architecture family before proceeding.",
                    "options": ["switching_step_down", "linear_regulation"],
                    "blocking": True,
                    "affected_blocks": ["b_converter"],
                }
            ]
        )

        result = ArchitecturePlanner(FakeLLMClient([output(draft)])).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.NEEDS_INPUT)
        self.assertIsNotNone(result.design_plan)
        self.assertEqual(result.requirement_issues[0].reason, PlanningIssueReason.ARCHITECTURE)
        self.assertEqual(result.requirement_issues[0].issue_type, "blocking_architecture_decision")

    def test_voltage_semantics_accept_matching_mapped_power_domain(self):
        result = ArchitecturePlanner(FakeLLMClient([output(valid_power_sensor_draft())])).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)

    def test_voltage_semantics_reject_mismatched_mapped_power_domain(self):
        result = ArchitecturePlanner(
            FakeLLMClient([output(set_output_domain_voltage(valid_power_sensor_draft(), 3.3))]),
            max_repair_attempts=0,
        ).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.FAILED)
        self.assertIsNone(result.design_plan)
        self.assertIn("voltage mismatch", result.requirement_issues[0].description)

    def test_voltage_semantics_can_repair_mismatched_output_domain(self):
        fake = FakeLLMClient(
            [
                output(set_output_domain_voltage(valid_power_sensor_draft(), 3.3)),
                output(valid_power_sensor_draft()),
            ]
        )

        result = ArchitecturePlanner(fake, max_repair_attempts=1).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        self.assertEqual(len(fake.prompts), 2)
        self.assertIn("voltage mismatch", fake.prompts[1])

    def test_voltage_semantic_retry_exhaustion_returns_failed_result(self):
        mismatch = output(set_output_domain_voltage(valid_power_sensor_draft(), 3.3))
        result = ArchitecturePlanner(FakeLLMClient([mismatch, mismatch]), max_repair_attempts=1).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.FAILED)
        self.assertIsNone(result.design_plan)
        self.assertIn("voltage mismatch", result.requirement_issues[0].description)

    def test_interface_semantics_accept_matching_protocol(self):
        result = ArchitecturePlanner(FakeLLMClient([output(valid_power_sensor_draft())])).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)

    def test_interface_semantics_reject_mismatched_protocol(self):
        result = ArchitecturePlanner(
            FakeLLMClient([output(set_interface_type(valid_power_sensor_draft(), "spi"))]),
            max_repair_attempts=0,
        ).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.FAILED)
        self.assertIsNone(result.design_plan)
        self.assertIn("protocol mismatch", result.requirement_issues[0].description)

    def test_interface_semantics_can_repair_mismatched_protocol(self):
        fake = FakeLLMClient(
            [
                output(set_interface_type(valid_power_sensor_draft(), "spi")),
                output(valid_power_sensor_draft()),
            ]
        )

        result = ArchitecturePlanner(fake, max_repair_attempts=1).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        self.assertEqual(len(fake.prompts), 2)
        self.assertIn("protocol mismatch", fake.prompts[1])

    def test_candidate_hard_requirement_needs_explicit_disposition(self):
        data = requirement_model_data()
        data["open_questions"] = []
        data["requirements"][2]["status"] = "candidate"
        model = RequirementModel.model_validate(data)
        draft = valid_power_sensor_draft()
        draft["requirement_mappings"] = [
            mapping for mapping in draft["requirement_mappings"] if mapping["requirement_id"] != "REQ_PWR_003"
        ]

        result = ArchitecturePlanner(FakeLLMClient([output(draft)]), max_repair_attempts=0).plan_architecture(model)

        self.assertEqual(result.status, PlanningResultStatus.FAILED)
        self.assertIn("REQ_PWR_003", result.requirement_issues[0].description)

    def test_rejected_requirement_does_not_force_coverage(self):
        data = requirement_model_data()
        data["open_questions"] = []
        data["requirements"][2]["status"] = "rejected"
        model = RequirementModel.model_validate(data)
        draft = valid_power_sensor_draft()
        draft["requirement_mappings"] = [
            mapping for mapping in draft["requirement_mappings"] if mapping["requirement_id"] != "REQ_PWR_003"
        ]

        result = ArchitecturePlanner(FakeLLMClient([output(draft)])).plan_architecture(model)

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)

    def test_replanning_preserves_plan_and_block_identity_where_practical(self):
        initial = ArchitecturePlanner(FakeLLMClient([output(valid_power_sensor_draft())])).plan_architecture(
            requirement_model(),
            planned_at=PLANNED_AT,
        ).design_plan

        data = requirement_model_data()
        data["open_questions"] = []
        data["revision"] = 2
        data["requirements"][1]["constraint"]["value"] = 3.3
        data["metadata"]["updated_at"] = "2026-08-17T00:00:00+05:30"
        updated_model = RequirementModel.model_validate(data)
        updated_draft = valid_power_sensor_draft(open_decisions=[])
        updated_draft["power_domains"][2]["name"] = "Regulated 3.3 V Rail"
        updated_draft["power_domains"][2]["voltage"]["value"] = 3.3

        result = ArchitecturePlanner(FakeLLMClient([output(updated_draft)])).plan_architecture(
            updated_model,
            existing_design_plan=initial,
            planned_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        )

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        self.assertEqual(result.design_plan.design_plan_id, initial.design_plan_id)
        self.assertEqual(result.design_plan.revision, initial.revision + 1)
        self.assertEqual(result.design_plan.functional_blocks[2].block_id, "BLOCK_PWR_001")
        self.assertEqual(result.design_plan.interfaces[0].interface_id, "IF_I2C_001")
        self.assertEqual(initial.revision, 1)
        self.assertEqual(initial.source_requirement_set.revision, 1)
        self.assertEqual(result.design_plan.source_requirement_set.revision, 2)
        self.assertEqual(result.design_plan.power_domains[2].voltage.value, 3.3)

    def test_invalid_llm_output_triggers_repair(self):
        fake = FakeLLMClient(["not json", output(valid_power_sensor_draft())])
        result = ArchitecturePlanner(fake, max_repair_attempts=1).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.ACCEPTED)
        self.assertEqual(len(fake.prompts), 2)
        self.assertIn("previous output was invalid", fake.prompts[1])

    def test_retry_exhaustion_returns_failed_result(self):
        fake = FakeLLMClient(["not json", "still not json"])
        result = ArchitecturePlanner(fake, max_repair_attempts=1).plan_architecture(requirement_model())

        self.assertEqual(result.status, PlanningResultStatus.FAILED)
        self.assertIsNone(result.design_plan)
        self.assertEqual(result.requirement_issues[0].reason, PlanningIssueReason.DRAFT)

    def test_component_leakage_from_llm_draft_fails_before_canonical_plan(self):
        draft = valid_power_sensor_draft()
        draft["architecture_decisions"][0]["choice"] = "TPS54331"

        result = ArchitecturePlanner(FakeLLMClient([output(draft)]), max_repair_attempts=0).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.FAILED)
        self.assertIsNone(result.design_plan)

    def test_unknown_requirement_ref_fails_before_acceptance(self):
        draft = valid_power_sensor_draft()
        draft["architecture_decisions"][0]["driven_by_requirements"].append("REQ_UNKNOWN_001")

        result = ArchitecturePlanner(FakeLLMClient([output(draft)]), max_repair_attempts=0).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.FAILED)
        self.assertIn("REQ_UNKNOWN_001", result.requirement_issues[0].description)

    def test_invalid_draft_ref_fails_before_acceptance(self):
        draft = valid_power_sensor_draft()
        draft["requirement_mappings"][0]["targets"][0]["draft_id"] = "b_missing"

        result = ArchitecturePlanner(FakeLLMClient([output(draft)]), max_repair_attempts=0).plan_architecture(
            requirement_model()
        )

        self.assertEqual(result.status, PlanningResultStatus.FAILED)
        self.assertIsNone(result.design_plan)

    def test_requirement_model_is_not_mutated_on_needs_input_or_planning(self):
        blocked = requirement_model(with_blocking_question=True)
        before_blocked = copy.deepcopy(blocked.model_dump(mode="json"))
        ArchitecturePlanner(FakeLLMClient([])).plan_architecture(blocked)
        self.assertEqual(blocked.model_dump(mode="json"), before_blocked)

        model = requirement_model()
        before = copy.deepcopy(model.model_dump(mode="json"))
        ArchitecturePlanner(FakeLLMClient([output(valid_power_sensor_draft())])).plan_architecture(model)
        self.assertEqual(model.model_dump(mode="json"), before)


if __name__ == "__main__":
    unittest.main()
