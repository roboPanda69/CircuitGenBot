import copy
import json
import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from schematic_ai.domain.requirements.models import (
    Assumption,
    Conflict,
    DerivedRequirement,
    Metadata,
    OpenQuestion,
    Origin,
    Relationship,
    Requirement,
    RequirementModel,
    SystemInfo,
    Target,
)


def base_requirement(requirement_id="REQ_PWR_001"):
    return Requirement(
        id=requirement_id,
        category="power",
        type="input_voltage",
        description="The circuit shall accept a nominal 12 V DC input.",
        target=Target(type="power_input", id="VIN"),
        constraint={"kind": "nominal", "value": 12, "unit": "V"},
        priority="required",
        enforcement="hard",
        origin=Origin(type="user", source_id="MSG_001"),
        status="confirmed",
        confidence=1.0,
        verification={
            "required": True,
            "preferred_methods": ["datasheet_constraint"],
            "acceptance": {"all_required_methods_must_pass": False},
        },
    )


def base_model(**overrides):
    data = {
        "requirement_set_id": "RQS_0001",
        "project_id": "PRJ_0001",
        "revision": 1,
        "system": SystemInfo(
            name="Temperature Sensor Board",
            description="12 V powered temperature sensing circuit",
            domain="general_electronics",
        ),
        "requirements": [base_requirement()],
        "derived_requirements": [],
        "assumptions": [],
        "open_questions": [],
        "conflicts": [],
        "metadata": Metadata(
            created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            created_by="requirement_interpreter",
        ),
    }
    data.update(overrides)
    return RequirementModel(**data)


class RequirementModelTests(unittest.TestCase):
    def test_valid_requirement_model(self):
        model = base_model()
        self.assertEqual(model.schema_version, "0.1")
        self.assertEqual(model.requirements[0].id, "REQ_PWR_001")

    def test_confidence_validation(self):
        data = base_requirement().model_dump(mode="json")
        data["confidence"] = 1.5
        with self.assertRaises(ValidationError):
            Requirement.model_validate(data)

        data = base_requirement().model_dump(mode="json")
        data["confidence"] = -0.1
        with self.assertRaises(ValidationError):
            Requirement.model_validate(data)

    def test_duplicate_requirement_ids_are_rejected(self):
        with self.assertRaises(ValidationError):
            base_model(requirements=[base_requirement("REQ_PWR_001"), base_requirement("REQ_PWR_001")])

    def test_duplicate_explicit_and_derived_requirement_ids_are_rejected(self):
        derived = DerivedRequirement(
            id="REQ_PWR_001",
            category="interface",
            type="i2c_pullup",
            description="The I2C bus shall provide suitable pull-up capability.",
            target=Target(type="interface", id="TEMP_SENSOR_BUS"),
            constraint={"kind": "text", "value": "Provide suitable pull-up capability."},
            priority="required",
            enforcement="hard",
            origin=Origin(type="engineering_rule", source_id="RULE_I2C_001"),
            confidence=0.9,
            derived_from=["REQ_PWR_001"],
            rule_id="RULE_I2C_001",
        )
        with self.assertRaises(ValidationError):
            base_model(derived_requirements=[derived])

    def test_assumptions_reference_requirements(self):
        assumption = Assumption(
            id="ASM_001",
            description="Ambient temperature assumed to be 25 degC.",
            parameter="ambient_temperature",
            value={"value": 25, "unit": "degC"},
            source="ai",
            confidence=0.5,
            impact="medium",
            affects_requirements=["REQ_PWR_001"],
        )
        model = base_model(assumptions=[assumption])
        self.assertEqual(model.assumptions[0].impact, "medium")

        bad_assumption = assumption.model_copy(update={"affects_requirements": ["REQ_UNKNOWN_001"]})
        with self.assertRaises(ValidationError):
            base_model(assumptions=[bad_assumption])

    def test_duplicate_assumption_ids_are_rejected(self):
        assumption = Assumption(
            id="ASM_001",
            description="Ambient temperature assumed to be 25 degC.",
            parameter="ambient_temperature",
            value={"value": 25, "unit": "degC"},
            source="ai",
            confidence=0.5,
            impact="medium",
            affects_requirements=["REQ_PWR_001"],
        )
        with self.assertRaises(ValidationError):
            base_model(assumptions=[assumption, assumption])

    def test_open_questions(self):
        question = OpenQuestion(
            id="Q_001",
            question="What input voltage range must the circuit tolerate?",
            reason="Only a nominal 12 V input was provided.",
            related_requirement_ids=["REQ_PWR_001"],
            importance="high",
            blocking=True,
            suggested_answers=["9-16 V"],
            status="open",
        )
        model = base_model(open_questions=[question])
        self.assertTrue(model.open_questions[0].blocking)

    def test_duplicate_open_question_ids_are_rejected(self):
        question = OpenQuestion(
            id="Q_001",
            question="What input voltage range must the circuit tolerate?",
            reason="Only a nominal 12 V input was provided.",
            related_requirement_ids=["REQ_PWR_001"],
            importance="high",
            blocking=True,
        )
        with self.assertRaises(ValidationError):
            base_model(open_questions=[question, question])

    def test_derived_requirements_reference_sources(self):
        derived = DerivedRequirement(
            id="DREQ_IF_001",
            category="interface",
            type="i2c_pullup",
            description="The I2C bus shall provide suitable pull-up capability.",
            target=Target(type="interface", id="TEMP_SENSOR_BUS"),
            constraint={"kind": "text", "value": "Provide suitable pull-up capability."},
            priority="required",
            enforcement="hard",
            origin=Origin(type="engineering_rule", source_id="RULE_I2C_001"),
            confidence=0.9,
            dependencies=[Relationship(type="derived_from", requirement_id="REQ_PWR_001")],
            derived_from=["REQ_PWR_001"],
            rule_id="RULE_I2C_001",
        )
        model = base_model(derived_requirements=[derived])
        self.assertEqual(model.derived_requirements[0].status, "derived")

        bad = derived.model_copy(update={"derived_from": ["REQ_UNKNOWN_001"]})
        with self.assertRaises(ValidationError):
            base_model(derived_requirements=[bad])

    def test_duplicate_derived_from_references_are_rejected(self):
        with self.assertRaises(ValidationError):
            DerivedRequirement(
                id="DREQ_IF_001",
                category="interface",
                type="i2c_pullup",
                description="The I2C bus shall provide suitable pull-up capability.",
                target=Target(type="interface", id="TEMP_SENSOR_BUS"),
                constraint={"kind": "text", "value": "Provide suitable pull-up capability."},
                priority="required",
                enforcement="hard",
                origin=Origin(type="engineering_rule", source_id="RULE_I2C_001"),
                confidence=0.9,
                derived_from=["REQ_PWR_001", "REQ_PWR_001"],
                rule_id="RULE_I2C_001",
            )

    def test_derived_requirement_cannot_derive_from_itself(self):
        derived = DerivedRequirement(
            id="DREQ_IF_001",
            category="interface",
            type="i2c_pullup",
            description="The I2C bus shall provide suitable pull-up capability.",
            target=Target(type="interface", id="TEMP_SENSOR_BUS"),
            constraint={"kind": "text", "value": "Provide suitable pull-up capability."},
            priority="required",
            enforcement="hard",
            origin=Origin(type="engineering_rule", source_id="RULE_I2C_001"),
            confidence=0.9,
            derived_from=["DREQ_IF_001"],
            rule_id="RULE_I2C_001",
        )
        with self.assertRaises(ValidationError):
            base_model(derived_requirements=[derived])

    def test_conflicts_reference_requirements(self):
        req1 = base_requirement("REQ_PWR_001")
        req2 = base_requirement("REQ_PWR_002").model_copy(
            update={
                "type": "logic_voltage",
                "description": "Logic voltage shall be 3.3 V.",
                "constraint": {"kind": "exact", "value": 3.3, "unit": "V"},
            }
        )
        conflict = Conflict(
            id="CONFLICT_001",
            requirement_ids=["REQ_PWR_001", "REQ_PWR_002"],
            type="mutually_incompatible",
            description="Logic voltage requirements specify incompatible values.",
            severity="blocking",
            resolution_status="unresolved",
        )
        model = base_model(requirements=[req1, req2], conflicts=[conflict])
        self.assertEqual(model.conflicts[0].severity, "blocking")

    def test_duplicate_conflict_ids_are_rejected(self):
        req1 = base_requirement("REQ_PWR_001")
        req2 = base_requirement("REQ_PWR_002")
        conflict = Conflict(
            id="CONFLICT_001",
            requirement_ids=["REQ_PWR_001", "REQ_PWR_002"],
            type="mutually_incompatible",
            description="Logic voltage requirements specify incompatible values.",
            severity="blocking",
        )
        with self.assertRaises(ValidationError):
            base_model(requirements=[req1, req2], conflicts=[conflict, conflict])

    def test_conflict_rejects_repeated_requirement_id(self):
        with self.assertRaises(ValidationError):
            Conflict(
                id="CONFLICT_001",
                requirement_ids=["REQ_PWR_001", "REQ_PWR_001"],
                type="mutually_incompatible",
                description="Repeated requirement.",
                severity="blocking",
            )

    def test_requirement_dependencies_reference_requirements(self):
        dependent = base_requirement("REQ_PWR_002").model_copy(
            update={"dependencies": [Relationship(type="requires", requirement_id="REQ_PWR_001")]}
        )
        model = base_model(requirements=[base_requirement("REQ_PWR_001"), dependent])
        self.assertEqual(model.requirements[1].dependencies[0].type, "requires")

        bad = dependent.model_copy(
            update={"dependencies": [Relationship(type="requires", requirement_id="REQ_UNKNOWN_001")]}
        )
        with self.assertRaises(ValidationError):
            base_model(requirements=[base_requirement("REQ_PWR_001"), bad])

    def test_direct_self_dependency_is_rejected(self):
        bad = base_requirement("REQ_PWR_001").model_copy(
            update={"dependencies": [Relationship(type="requires", requirement_id="REQ_PWR_001")]}
        )
        with self.assertRaises(ValidationError):
            base_model(requirements=[bad])

    def test_blank_target_ids_are_rejected(self):
        with self.assertRaises(ValidationError):
            Target(type="power_output", id="")

        with self.assertRaises(ValidationError):
            Target(type="power_output", id="   ")

    def test_serialization_round_trip(self):
        model = base_model()
        raw = model.model_dump_json()
        restored = RequirementModel.model_validate_json(raw)
        self.assertEqual(restored.model_dump(mode="json"), model.model_dump(mode="json"))

    def test_deserialization_from_dict(self):
        data = base_model().model_dump(mode="json")
        restored = RequirementModel.model_validate(data)
        self.assertEqual(restored.requirement_set_id, "RQS_0001")

    def test_schema_generation(self):
        schema = RequirementModel.model_json_schema()
        self.assertEqual(schema["title"], "RequirementModel")
        self.assertIn("$defs", schema)

    def test_metadata_requires_timezone_aware_timestamps(self):
        with self.assertRaises(ValidationError):
            Metadata(
                created_at=datetime(2026, 8, 15),
                updated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
                created_by="requirement_interpreter",
            )

    def test_metadata_rejects_updated_at_before_created_at(self):
        with self.assertRaises(ValidationError):
            Metadata(
                created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
                created_by="requirement_interpreter",
            )

    def test_metadata_accepts_chronological_timestamps(self):
        metadata = Metadata(
            created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            created_by="requirement_interpreter",
        )
        self.assertGreaterEqual(metadata.updated_at, metadata.created_at)

    def test_example_scenario_semantics(self):
        with open("examples/requirement_model_v0_1.json", encoding="utf-8") as handle:
            data = json.load(handle)
        model = RequirementModel.model_validate(data)
        self.assertEqual(len(model.requirements), 6)
        self.assertEqual(model.requirements[0].group_id, "REQGRP_PWR_IN_01")
        self.assertEqual(model.assumptions[0].source, "ai")
        self.assertEqual(model.derived_requirements[0].derived_from, ["REQ_IF_001"])
        self.assertEqual(model.assumptions[0].id, "ASM_001")
        self.assertTrue(model.open_questions[0].blocking)

    def test_unknown_internal_reference_is_rejected(self):
        data = base_model().model_dump(mode="json")
        bad = copy.deepcopy(data)
        bad["conflicts"] = [
            {
                "id": "CONFLICT_001",
                "requirement_ids": ["REQ_PWR_001", "REQ_UNKNOWN_001"],
                "type": "mutually_incompatible",
                "description": "Unknown reference.",
                "severity": "blocking",
                "resolution_status": "unresolved",
            }
        ]
        with self.assertRaises(ValidationError):
            RequirementModel.model_validate(bad)


if __name__ == "__main__":
    unittest.main()
