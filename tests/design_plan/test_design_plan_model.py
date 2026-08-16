import copy
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from schematic_ai.domain.design_plan import (
    DesignPlan,
    DesignPlanContextValidationError,
    FunctionalBlock,
    FunctionalPort,
    validate_design_plan_against_requirements,
)
from schematic_ai.domain.requirements.models import RequirementModel


ROOT = Path(__file__).resolve().parents[2]
DESIGN_PLAN_PATH = ROOT / "examples" / "design_plan_v0_1.json"
REQUIREMENT_MODEL_PATH = ROOT / "examples" / "requirement_model_v0_1.json"


def design_plan_data():
    return json.loads(DESIGN_PLAN_PATH.read_text(encoding="utf-8"))


def requirement_model_data():
    return json.loads(REQUIREMENT_MODEL_PATH.read_text(encoding="utf-8"))


def design_plan():
    return DesignPlan.model_validate(design_plan_data())


def requirement_model():
    return RequirementModel.model_validate(requirement_model_data())


class DesignPlanModelTests(unittest.TestCase):
    def test_valid_design_plan_example(self):
        plan = design_plan()
        self.assertEqual(plan.schema_version, "0.1")
        self.assertEqual(plan.functional_blocks[2].topology_class, "switching_step_down")
        self.assertEqual(plan.interfaces[0].type, "i2c")
        self.assertEqual(plan.power_domains[2].power_domain_id, "PWRDOM_5V")
        validate_design_plan_against_requirements(plan, requirement_model())

    def test_core_models_can_be_created_without_component_details(self):
        block = FunctionalBlock(
            block_id="BLOCK_PWR_001",
            type="power_conversion",
            name="Power Conversion",
            purpose="Convert one logical power domain to another.",
            topology_class="switching_step_down",
            inputs=[
                FunctionalPort(
                    port_id="PORT_IN",
                    name="input_power",
                    kind="power",
                    direction="input",
                )
            ],
            outputs=[
                FunctionalPort(
                    port_id="PORT_OUT",
                    name="output_power",
                    kind="power",
                    direction="output",
                )
            ],
        )
        self.assertEqual(block.topology_class, "switching_step_down")
        self.assertFalse(hasattr(block, "manufacturer"))

    def test_component_specific_fields_are_rejected(self):
        data = design_plan_data()
        data["functional_blocks"][0]["manufacturer"] = "Example Semiconductor"
        with self.assertRaises(ValidationError):
            DesignPlan.model_validate(data)

    def test_component_leakage_in_topology_class_is_rejected(self):
        invalid_topologies = [
            "TPS54331",
            "LM2596",
            "TPS62160",
            "R1 = 10k",
            "C1 = 22uF",
            "L1 = 10uH",
            "GPIO21",
            "NET_5V",
            "Device:R",
            "Package_TO_SOT_SMD:SOT-23",
        ]
        for topology in invalid_topologies:
            with self.subTest(topology=topology):
                data = design_plan_data()
                data["functional_blocks"][2]["topology_class"] = topology
                with self.assertRaises(ValidationError):
                    DesignPlan.model_validate(data)

    def test_valid_architecture_topology_classes_are_accepted(self):
        for topology in ["switching_step_down", "linear_regulation", "interface_bridge"]:
            with self.subTest(topology=topology):
                data = design_plan_data()
                data["functional_blocks"][2]["topology_class"] = topology
                plan = DesignPlan.model_validate(data)
                self.assertEqual(plan.functional_blocks[2].topology_class, topology)

    def test_topology_class_remains_optional(self):
        data = design_plan_data()
        data["functional_blocks"][2]["topology_class"] = None
        plan = DesignPlan.model_validate(data)
        self.assertIsNone(plan.functional_blocks[2].topology_class)

    def test_architecture_decision_accepts_architecture_level_choices(self):
        cases = [
            ("topology_choice", "switching_step_down"),
            ("topology_choice", "linear_regulation"),
            ("topology_choice", "isolated_power_conversion"),
            ("interface_strategy", "direct_interface"),
            ("interface_strategy", "interface_bridge"),
            ("interface_strategy", "level_translation"),
        ]
        for decision_type, choice in cases:
            with self.subTest(decision_type=decision_type, choice=choice):
                data = design_plan_data()
                data["architecture_decisions"][0]["type"] = decision_type
                data["architecture_decisions"][0]["choice"] = choice
                DesignPlan.model_validate(data)

    def test_architecture_decision_rejects_implementation_choices(self):
        invalid_choices = [
            "TPS54331",
            "LM2596",
            "TPS62160",
            "R1 = 10k",
            "C1 = 22uF",
            "L1 = 10uH",
            "GPIO21",
            "NET_5V",
            "Device:R",
            "Package_SO:SOIC-8",
        ]
        for choice in invalid_choices:
            with self.subTest(choice=choice):
                data = design_plan_data()
                data["architecture_decisions"][0]["choice"] = choice
                with self.assertRaises(ValidationError):
                    DesignPlan.model_validate(data)

    def test_architecture_decision_rejects_incompatible_choice_for_type(self):
        data = design_plan_data()
        data["architecture_decisions"][0]["type"] = "interface_strategy"
        data["architecture_decisions"][0]["choice"] = "switching_step_down"
        with self.assertRaises(ValidationError):
            DesignPlan.model_validate(data)

    def test_open_decision_options_accept_architecture_choices(self):
        data = design_plan_data()
        data["open_decisions"][0]["options"] = ["direct_interface", "interface_bridge"]
        plan = DesignPlan.model_validate(data)
        self.assertEqual(plan.open_decisions[0].options, ["direct_interface", "interface_bridge"])

    def test_open_decision_options_reject_implementation_choices(self):
        invalid_option_sets = [
            ["TPS54331", "LM2596"],
            ["R1 = 10k", "C1 = 22uF"],
            ["NET_5V"],
            ["Device:R"],
            ["Package_SO:SOIC-8"],
        ]
        for options in invalid_option_sets:
            with self.subTest(options=options):
                data = design_plan_data()
                data["open_decisions"][0]["options"] = options
                with self.assertRaises(ValidationError):
                    DesignPlan.model_validate(data)

    def test_json_round_trip(self):
        plan = design_plan()
        restored = DesignPlan.model_validate_json(plan.model_dump_json())
        self.assertEqual(restored.model_dump(mode="json"), plan.model_dump(mode="json"))

    def test_schema_generation(self):
        schema = DesignPlan.model_json_schema()
        self.assertEqual(schema["title"], "DesignPlan")
        self.assertIn("$defs", schema)


class DesignPlanIdentityValidationTests(unittest.TestCase):
    def assert_invalid(self, mutator):
        data = design_plan_data()
        mutator(data)
        with self.assertRaises(ValidationError):
            DesignPlan.model_validate(data)

    def test_duplicate_block_id_rejected(self):
        self.assert_invalid(lambda data: data["functional_blocks"].append(copy.deepcopy(data["functional_blocks"][0])))

    def test_duplicate_port_id_rejected(self):
        def mutate(data):
            data["functional_blocks"][1]["inputs"][0]["port_id"] = "PORT_INPUT_RAW_OUT"

        self.assert_invalid(mutate)

    def test_duplicate_connection_id_rejected(self):
        self.assert_invalid(lambda data: data["block_connections"].append(copy.deepcopy(data["block_connections"][0])))

    def test_duplicate_power_domain_id_rejected(self):
        self.assert_invalid(lambda data: data["power_domains"].append(copy.deepcopy(data["power_domains"][0])))

    def test_duplicate_interface_id_rejected(self):
        self.assert_invalid(lambda data: data["interfaces"].append(copy.deepcopy(data["interfaces"][0])))

    def test_duplicate_mapping_id_rejected(self):
        self.assert_invalid(lambda data: data["requirement_mappings"].append(copy.deepcopy(data["requirement_mappings"][0])))

    def test_duplicate_decision_id_rejected(self):
        self.assert_invalid(lambda data: data["architecture_decisions"].append(copy.deepcopy(data["architecture_decisions"][0])))

    def test_duplicate_assumption_id_rejected(self):
        self.assert_invalid(lambda data: data["assumptions"].append(copy.deepcopy(data["assumptions"][0])))

    def test_duplicate_open_decision_id_rejected(self):
        self.assert_invalid(lambda data: data["open_decisions"].append(copy.deepcopy(data["open_decisions"][0])))


class DesignPlanDanglingReferenceTests(unittest.TestCase):
    def assert_invalid(self, mutator):
        data = design_plan_data()
        mutator(data)
        with self.assertRaises(ValidationError):
            DesignPlan.model_validate(data)

    def test_connection_missing_block_rejected(self):
        self.assert_invalid(lambda data: data["block_connections"][0]["source"].update({"block_id": "BLOCK_MISSING"}))

    def test_connection_missing_port_rejected(self):
        self.assert_invalid(lambda data: data["block_connections"][0]["source"].update({"port_id": "PORT_MISSING"}))

    def test_connection_identical_endpoint_rejected(self):
        def mutate(data):
            data["block_connections"][0]["target"] = copy.deepcopy(data["block_connections"][0]["source"])

        self.assert_invalid(mutate)

    def test_connection_input_to_input_rejected(self):
        self.assert_invalid(lambda data: data["block_connections"][0]["source"].update({"port_id": "PORT_INPUT_RAW_IN"}))

    def test_power_domain_source_missing_rejected(self):
        self.assert_invalid(lambda data: data["power_domains"][0].update({"source_block": "BLOCK_MISSING"}))

    def test_power_domain_consumer_missing_rejected(self):
        self.assert_invalid(lambda data: data["power_domains"][0]["consumer_blocks"].append("BLOCK_MISSING"))

    def test_power_domain_duplicate_consumer_rejected(self):
        self.assert_invalid(lambda data: data["power_domains"][2]["consumer_blocks"].append("BLOCK_SENSOR_001"))

    def test_interface_participant_missing_rejected(self):
        self.assert_invalid(lambda data: data["interfaces"][0]["participants"].append("BLOCK_MISSING"))

    def test_interface_duplicate_participant_rejected(self):
        self.assert_invalid(lambda data: data["interfaces"][0]["participants"].append("BLOCK_SENSOR_001"))

    def test_interface_power_domain_missing_rejected(self):
        self.assert_invalid(lambda data: data["interfaces"][0].update({"power_domain": "PWRDOM_MISSING"}))

    def test_mapping_target_missing_rejected(self):
        self.assert_invalid(lambda data: data["requirement_mappings"][0]["implemented_by"][0].update({"id": "BLOCK_MISSING"}))

    def test_decision_target_missing_rejected(self):
        self.assert_invalid(lambda data: data["architecture_decisions"][0]["target"].update({"id": "BLOCK_MISSING"}))

    def test_assumption_affected_block_missing_rejected(self):
        self.assert_invalid(lambda data: data["assumptions"][0]["affected_blocks"].append("BLOCK_MISSING"))

    def test_open_decision_affected_block_missing_rejected(self):
        self.assert_invalid(lambda data: data["open_decisions"][0]["affected_blocks"].append("BLOCK_MISSING"))

    def test_open_decision_duplicate_options_rejected(self):
        self.assert_invalid(lambda data: data["open_decisions"][0]["options"].append("direct_i2c"))

    def test_cycles_are_not_generically_rejected(self):
        data = design_plan_data()
        data["block_connections"].append(
            {
                "connection_id": "CONN_004",
                "source": {"block_id": "BLOCK_SENSOR_001", "port_id": "PORT_SENSOR_I2C"},
                "target": {"block_id": "BLOCK_HOST_IF_001", "port_id": "PORT_HOST_I2C"},
                "kind": "communication",
                "description": "Bidirectional logical I2C communication.",
            }
        )
        DesignPlan.model_validate(data)


class DesignPlanContextValidationTests(unittest.TestCase):
    def _with_requirement_status_and_mapping(
        self,
        *,
        requirement_id: str,
        status: str,
        enforcement: str = "hard",
        include_mapping: bool,
        mapping_status: str = "unresolved",
    ):
        req_data = requirement_model_data()
        for requirement in req_data["requirements"]:
            if requirement["id"] == requirement_id:
                requirement["status"] = status
                requirement["enforcement"] = enforcement
                break
        plan_data = design_plan_data()
        plan_data["requirement_mappings"] = [
            mapping for mapping in plan_data["requirement_mappings"] if mapping["requirement_id"] != requirement_id
        ]
        if include_mapping:
            implemented_by = []
            if mapping_status in {"mapped", "partially_mapped"}:
                implemented_by = [{"type": "functional_block", "id": "BLOCK_PWR_001"}]
            plan_data["requirement_mappings"].append(
                {
                    "mapping_id": "MAP_EXTRA_001",
                    "requirement_id": requirement_id,
                    "implemented_by": implemented_by,
                    "status": mapping_status,
                }
            )
        return DesignPlan.model_validate(plan_data), RequirementModel.model_validate(req_data)

    def test_source_requirement_set_id_mismatch_rejected(self):
        plan = design_plan()
        req = requirement_model()
        data = plan.model_dump(mode="json")
        data["source_requirement_set"]["requirement_set_id"] = "RQS_OTHER"
        with self.assertRaises(DesignPlanContextValidationError):
            validate_design_plan_against_requirements(DesignPlan.model_validate(data), req)

    def test_source_revision_mismatch_rejected(self):
        plan = design_plan()
        req = requirement_model()
        data = plan.model_dump(mode="json")
        data["source_requirement_set"]["revision"] = 99
        with self.assertRaises(DesignPlanContextValidationError):
            validate_design_plan_against_requirements(DesignPlan.model_validate(data), req)

    def test_mapping_unknown_requirement_rejected(self):
        plan_data = design_plan_data()
        plan_data["requirement_mappings"][0]["requirement_id"] = "REQ_UNKNOWN_001"
        with self.assertRaises(DesignPlanContextValidationError):
            validate_design_plan_against_requirements(DesignPlan.model_validate(plan_data), requirement_model())

    def test_decision_unknown_requirement_rejected(self):
        plan_data = design_plan_data()
        plan_data["architecture_decisions"][0]["driven_by_requirements"].append("REQ_UNKNOWN_001")
        with self.assertRaises(DesignPlanContextValidationError):
            validate_design_plan_against_requirements(DesignPlan.model_validate(plan_data), requirement_model())

    def test_missing_active_hard_requirement_mapping_rejected(self):
        plan_data = design_plan_data()
        plan_data["requirement_mappings"] = [
            mapping for mapping in plan_data["requirement_mappings"] if mapping["requirement_id"] != "REQ_PWR_003"
        ]
        with self.assertRaises(DesignPlanContextValidationError):
            validate_design_plan_against_requirements(DesignPlan.model_validate(plan_data), requirement_model())

    def test_candidate_hard_requirement_without_mapping_rejected(self):
        plan, req = self._with_requirement_status_and_mapping(
            requirement_id="REQ_PWR_003",
            status="candidate",
            include_mapping=False,
        )
        with self.assertRaises(DesignPlanContextValidationError):
            validate_design_plan_against_requirements(plan, req)

    def test_candidate_hard_requirement_unresolved_is_valid(self):
        plan, req = self._with_requirement_status_and_mapping(
            requirement_id="REQ_PWR_003",
            status="candidate",
            include_mapping=True,
            mapping_status="unresolved",
        )
        validate_design_plan_against_requirements(plan, req)

    def test_needs_clarification_hard_requirement_without_mapping_rejected(self):
        plan, req = self._with_requirement_status_and_mapping(
            requirement_id="REQ_PWR_003",
            status="needs_clarification",
            include_mapping=False,
        )
        with self.assertRaises(DesignPlanContextValidationError):
            validate_design_plan_against_requirements(plan, req)

    def test_needs_clarification_hard_requirement_unresolved_is_valid(self):
        plan, req = self._with_requirement_status_and_mapping(
            requirement_id="REQ_PWR_003",
            status="needs_clarification",
            include_mapping=True,
            mapping_status="unresolved",
        )
        validate_design_plan_against_requirements(plan, req)

    def test_confirmed_hard_requirement_mapped_is_valid(self):
        plan, req = self._with_requirement_status_and_mapping(
            requirement_id="REQ_PWR_003",
            status="confirmed",
            include_mapping=True,
            mapping_status="mapped",
        )
        mapping = plan.requirement_mappings[-1]
        self.assertEqual(mapping.status, "mapped")
        validate_design_plan_against_requirements(plan, req)

    def test_derived_hard_requirement_mapped_is_valid(self):
        plan_data = design_plan_data()
        req_data = requirement_model_data()
        for mapping in plan_data["requirement_mappings"]:
            if mapping["requirement_id"] == "DREQ_IF_001":
                mapping["implemented_by"] = [
                    {"type": "architecture_decision", "id": "DEC_001"}
                ]
                mapping["status"] = "mapped"
        validate_design_plan_against_requirements(
            DesignPlan.model_validate(plan_data),
            RequirementModel.model_validate(req_data),
        )

    def test_unresolved_active_hard_requirement_counts_as_explicit_disposition(self):
        plan_data = design_plan_data()
        for mapping in plan_data["requirement_mappings"]:
            if mapping["requirement_id"] == "REQ_PWR_003":
                mapping["implemented_by"] = []
                mapping["status"] = "unresolved"
        validate_design_plan_against_requirements(DesignPlan.model_validate(plan_data), requirement_model())

    def test_rejected_requirement_does_not_force_coverage(self):
        req_data = requirement_model_data()
        req_data["requirements"][2]["status"] = "rejected"
        plan_data = design_plan_data()
        plan_data["requirement_mappings"] = [
            mapping for mapping in plan_data["requirement_mappings"] if mapping["requirement_id"] != "REQ_PWR_003"
        ]
        validate_design_plan_against_requirements(
            DesignPlan.model_validate(plan_data),
            RequirementModel.model_validate(req_data),
        )

    def test_superseded_requirement_does_not_force_coverage(self):
        req_data = requirement_model_data()
        req_data["requirements"][2]["status"] = "superseded"
        plan_data = design_plan_data()
        plan_data["requirement_mappings"] = [
            mapping for mapping in plan_data["requirement_mappings"] if mapping["requirement_id"] != "REQ_PWR_003"
        ]
        validate_design_plan_against_requirements(
            DesignPlan.model_validate(plan_data),
            RequirementModel.model_validate(req_data),
        )

    def test_soft_requirement_does_not_force_coverage(self):
        plan, req = self._with_requirement_status_and_mapping(
            requirement_id="REQ_PWR_003",
            status="confirmed",
            enforcement="soft",
            include_mapping=False,
        )
        validate_design_plan_against_requirements(plan, req)

    def test_partially_mapped_counts_as_explicit_disposition(self):
        plan, req = self._with_requirement_status_and_mapping(
            requirement_id="REQ_PWR_003",
            status="candidate",
            include_mapping=True,
            mapping_status="partially_mapped",
        )
        validate_design_plan_against_requirements(plan, req)


if __name__ == "__main__":
    unittest.main()
