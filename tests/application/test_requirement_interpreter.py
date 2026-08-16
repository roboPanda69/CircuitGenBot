import json
import unittest
from datetime import datetime, timezone

from schematic_ai.application.requirements import MessageEnvelope, RequirementInterpreter
from schematic_ai.application.requirements.interpreter import RequirementInterpretationError


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


def extraction(requirements, open_questions=None, assumptions=None):
    return output(
        {
            "system_name": "Test Board",
            "system_description": "Generated from user message.",
            "requirements": requirements,
            "assumptions": assumptions or [],
            "open_questions": open_questions or [],
        }
    )


def message(text, message_id="MSG_001"):
    return MessageEnvelope(message_id=message_id, project_id="PRJ_0001", text=text)


CREATED_AT = datetime(2026, 8, 15, tzinfo=timezone.utc)
UPDATED_AT = datetime(2026, 8, 16, tzinfo=timezone.utc)


def power_supply_requirements(unit_v="V", unit_a="A"):
    return [
        {
            "category": "power",
            "type": "input_voltage",
            "constraint": {"kind": "nominal", "value": 12, "unit": unit_v},
        },
        {
            "category": "power",
            "type": "output_voltage",
            "constraint": {"kind": "nominal", "value": 5, "unit": unit_v},
        },
        {
            "category": "power",
            "type": "output_current",
            "constraint": {"kind": "minimum", "value": 2, "unit": unit_a},
        },
    ]


class RequirementInterpreterTests(unittest.TestCase):
    def test_basic_power_requirement(self):
        interpreter = RequirementInterpreter(FakeLLMClient([extraction(power_supply_requirements())]))
        result = interpreter.interpret_new(message("Make a 12V to 5V 2A power supply."))

        self.assertTrue(result.accepted)
        requirements = {requirement.type: requirement for requirement in result.model.requirements}
        self.assertEqual(requirements["input_voltage"].constraint.kind, "nominal")
        self.assertEqual(requirements["input_voltage"].constraint.value, 12)
        self.assertEqual(requirements["input_voltage"].constraint.unit, "V")
        self.assertEqual(requirements["output_voltage"].constraint.value, 5)
        self.assertEqual(requirements["output_current"].constraint.kind, "minimum")
        self.assertEqual(requirements["output_current"].constraint.value, 2)
        self.assertEqual(requirements["output_current"].constraint.unit, "A")

    def test_empty_extraction_is_never_accepted(self):
        interpreter = RequirementInterpreter(FakeLLMClient([extraction([])]))
        result = interpreter.interpret_new(message("Make me a circuit."))

        self.assertFalse(result.accepted)
        self.assertEqual(result.status, "needs_input")
        self.assertEqual(len(result.model.requirements), 0)
        self.assertEqual(len(result.model.open_questions), 1)
        self.assertEqual(result.model.open_questions[0].id, "Q_001")
        self.assertIn("What should the circuit do?", result.model.open_questions[0].question)

    def test_empty_extraction_with_question_needs_input_not_failure(self):
        interpreter = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [],
                        open_questions=[
                            {
                                "question": "What kind of power board do you need?",
                                "reason": "No specific voltage, current, or function was provided.",
                                "blocking": True,
                                "importance": "high",
                            }
                        ],
                    )
                ]
            )
        )
        result = interpreter.interpret_new(message("I need some kind of power board."))

        self.assertEqual(result.status, "needs_input")
        self.assertEqual(len(result.model.requirements), 0)
        self.assertEqual(result.model.open_questions[0].question, "What kind of power board do you need?")

    def test_natural_wording_units_are_normalized(self):
        interpreter = RequirementInterpreter(FakeLLMClient([extraction(power_supply_requirements("volts", "amps"))]))
        result = interpreter.interpret_new(
            message(
                "I want something I can run from a normal 12 volt adapter and I need about 5 volts out with at least 2 amps available."
            )
        )

        requirements = {requirement.type: requirement for requirement in result.model.requirements}
        self.assertEqual(requirements["input_voltage"].constraint.unit, "V")
        self.assertEqual(requirements["output_current"].constraint.unit, "A")

    def test_range_requirement(self):
        interpreter = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [
                            {
                                "category": "power",
                                "type": "input_voltage",
                                "constraint": {
                                    "kind": "range",
                                    "minimum": 9,
                                    "maximum": 16,
                                    "unit": "volts",
                                },
                            }
                        ]
                    )
                ]
            )
        )
        result = interpreter.interpret_new(message("The input can vary between 9 and 16 volts."))

        requirement = result.model.requirements[0]
        self.assertEqual(requirement.constraint.kind, "range")
        self.assertEqual(requirement.constraint.minimum, 9)
        self.assertEqual(requirement.constraint.maximum, 16)
        self.assertEqual(requirement.constraint.unit, "V")

    def test_maximum_requirement(self):
        interpreter = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [
                            {
                                "category": "power",
                                "type": "power_consumption",
                                "constraint": {"kind": "maximum", "value": 100, "unit": "mA"},
                            }
                        ]
                    )
                ]
            )
        )
        result = interpreter.interpret_new(message("The sensor must consume no more than 100 mA."))

        requirement = result.model.requirements[0]
        self.assertEqual(requirement.constraint.kind, "maximum")
        self.assertEqual(requirement.constraint.value, 100)
        self.assertEqual(requirement.constraint.unit, "mA")

    def test_tolerance_requirement(self):
        interpreter = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [
                            {
                                "category": "power",
                                "type": "output_voltage",
                                "constraint": {
                                    "kind": "nominal_with_tolerance",
                                    "nominal": 5,
                                    "unit": "V",
                                    "tolerance": {"type": "percent", "minus": 2, "plus": 2},
                                },
                            },
                            {
                                "category": "power",
                                "type": "output_current",
                                "constraint": {"kind": "minimum", "value": 1, "unit": "A"},
                            },
                        ]
                    )
                ]
            )
        )
        result = interpreter.interpret_new(message("The output should be 5 V +/-2%."))

        requirement = next(req for req in result.model.requirements if req.type == "output_voltage")
        self.assertEqual(requirement.constraint.kind, "nominal_with_tolerance")
        self.assertEqual(requirement.constraint.tolerance.plus, 2)

    def test_protection_requirement(self):
        interpreter = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [
                            {
                                "category": "protection",
                                "type": "reverse_polarity_protection",
                                "constraint": {"kind": "boolean", "value": True},
                            }
                        ]
                    )
                ]
            )
        )
        result = interpreter.interpret_new(message("Add reverse polarity protection."))

        requirement = result.model.requirements[0]
        self.assertEqual(requirement.category, "protection")
        self.assertEqual(requirement.constraint.kind, "boolean")
        self.assertTrue(requirement.constraint.value)

    def test_preference_requirement(self):
        interpreter = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [
                            {
                                "category": "user_preference",
                                "type": "preferred_manufacturer",
                                "constraint": {
                                    "kind": "enum_preference",
                                    "preferred": ["Texas Instruments"],
                                },
                            }
                        ]
                    )
                ]
            )
        )
        result = interpreter.interpret_new(message("Prefer Texas Instruments parts if possible."))

        requirement = result.model.requirements[0]
        self.assertEqual(requirement.priority, "preference")
        self.assertEqual(requirement.enforcement, "soft")

    def test_missing_output_current_adds_open_question(self):
        interpreter = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [
                            {
                                "category": "power",
                                "type": "input_voltage",
                                "constraint": {"kind": "nominal", "value": 12, "unit": "V"},
                            },
                            {
                                "category": "power",
                                "type": "output_voltage",
                                "constraint": {"kind": "nominal", "value": 5, "unit": "V"},
                            },
                        ]
                    )
                ]
            )
        )
        result = interpreter.interpret_new(message("Make a 12 V to 5 V converter."))

        self.assertEqual(result.status, "needs_input")
        self.assertEqual(result.open_questions[0].question, "What output current is required?")
        self.assertTrue(result.open_questions[0].blocking)

    def test_follow_up_replacement_preserves_requirement_id_and_increments_revision(self):
        initial = RequirementInterpreter(FakeLLMClient([extraction(power_supply_requirements())])).interpret_new(
            message("Make a 12V to 5V 2A power supply."),
            created_at=CREATED_AT,
        ).model
        change = output(
            {
                "operations": [
                    {
                        "operation": "replace_requirement_constraint",
                        "target_requirement_id": "REQ_PWR_002",
                        "new_constraint": {"kind": "nominal", "value": 3.3, "unit": "V"},
                    }
                ]
            }
        )
        interpreter = RequirementInterpreter(FakeLLMClient([change]))
        updated = interpreter.interpret_change(
            message("Actually make the output 3.3 V.", "MSG_002"),
            initial,
            updated_at=UPDATED_AT,
        ).model

        output_voltage = [req for req in updated.requirements if req.type == "output_voltage"]
        self.assertEqual(len(output_voltage), 1)
        self.assertEqual(output_voltage[0].id, "REQ_PWR_002")
        self.assertEqual(output_voltage[0].constraint.value, 3.3)
        self.assertEqual(updated.revision, initial.revision + 1)
        self.assertEqual(next(req for req in initial.requirements if req.id == "REQ_PWR_002").constraint.value, 5)

    def test_follow_up_addition_allocates_new_id(self):
        initial = RequirementInterpreter(FakeLLMClient([extraction(power_supply_requirements())])).interpret_new(
            message("Make a 12V to 5V 2A power supply."),
            created_at=CREATED_AT,
        ).model
        addition = output(
            {
                "operations": [
                    {
                        "operation": "add_requirement",
                        "requirement": {
                            "category": "protection",
                            "type": "reverse_polarity_protection",
                            "constraint": {"kind": "boolean", "value": True},
                        },
                    }
                ]
            }
        )
        interpreter = RequirementInterpreter(FakeLLMClient([addition]))
        updated = interpreter.interpret_change(message("Also add reverse polarity protection.", "MSG_002"), initial).model

        self.assertEqual(len(initial.requirements), 3)
        protection = next(req for req in updated.requirements if req.type == "reverse_polarity_protection")
        self.assertEqual(protection.id, "REQ_PROT_001")
        self.assertEqual(updated.revision, initial.revision + 1)

    def test_ambiguous_modification_returns_open_question_without_guessing(self):
        initial = RequirementInterpreter(FakeLLMClient([extraction(power_supply_requirements())])).interpret_new(
            message("Make a 12V to 5V 2A power supply."),
            created_at=CREATED_AT,
        ).model
        ambiguity = output(
            {
                "operations": [
                    {
                        "operation": "ask_open_question",
                        "question": {
                            "question": "Which voltage should be changed?",
                            "reason": "Both input and output voltage requirements exist.",
                            "blocking": True,
                            "importance": "high",
                            "suggested_answers": ["input voltage", "output voltage"],
                        },
                    }
                ]
            }
        )
        interpreter = RequirementInterpreter(FakeLLMClient([ambiguity]))
        result = interpreter.interpret_change(message("Increase the voltage.", "MSG_002"), initial)

        self.assertEqual(result.status, "needs_input")
        self.assertIsNotNone(result.model)
        self.assertEqual(result.model.revision, initial.revision + 1)
        self.assertEqual(len(initial.open_questions), 0)
        self.assertEqual(len(result.model.open_questions), 1)
        self.assertEqual(result.open_questions[0].question, "Which voltage should be changed?")
        self.assertEqual(result.model.open_questions[0].question, "Which voltage should be changed?")

    def test_follow_up_question_persists_in_canonical_model(self):
        initial = RequirementInterpreter(FakeLLMClient([extraction(power_supply_requirements())])).interpret_new(
            message("Make a 12V to 5V 2A power supply."),
            created_at=CREATED_AT,
        ).model
        question_only = output(
            {
                "operations": [
                    {
                        "operation": "ask_open_question",
                        "question": {
                            "question": "What output ripple limit is acceptable?",
                            "reason": "Ripple requirements affect regulator and filtering choices.",
                            "blocking": True,
                            "importance": "high",
                        },
                    }
                ]
            }
        )
        result = RequirementInterpreter(FakeLLMClient([question_only])).interpret_change(
            message("Make it very clean.", "MSG_002"),
            initial,
            updated_at=UPDATED_AT,
        )

        self.assertEqual(result.status, "needs_input")
        self.assertEqual(result.model.revision, initial.revision + 1)
        self.assertEqual(len(initial.open_questions), 0)
        self.assertEqual(len(result.model.open_questions), 1)
        self.assertEqual(result.model.open_questions[0].id, "Q_001")
        self.assertEqual(result.open_questions[0].id, "Q_001")

    def test_mixed_follow_up_edit_and_question_persist(self):
        initial = RequirementInterpreter(FakeLLMClient([extraction(power_supply_requirements())])).interpret_new(
            message("Make a 12V to 5V 2A power supply."),
            created_at=CREATED_AT,
        ).model
        mixed = output(
            {
                "operations": [
                    {
                        "operation": "replace_requirement_constraint",
                        "target_requirement_id": "REQ_PWR_002",
                        "new_constraint": {"kind": "nominal", "value": 3.3, "unit": "V"},
                    },
                    {
                        "operation": "ask_open_question",
                        "question": {
                            "question": "What output current is required at 3.3 V?",
                            "reason": "The voltage changed and current is needed for power-stage selection.",
                            "blocking": True,
                            "importance": "high",
                        },
                    },
                ]
            }
        )
        result = RequirementInterpreter(FakeLLMClient([mixed])).interpret_change(
            message("Actually make the output 3.3 V, but I am not sure about current.", "MSG_002"),
            initial,
            updated_at=UPDATED_AT,
        )

        output_voltage = next(req for req in result.model.requirements if req.id == "REQ_PWR_002")
        self.assertEqual(result.status, "needs_input")
        self.assertEqual(output_voltage.constraint.value, 3.3)
        self.assertEqual(result.model.revision, initial.revision + 1)
        self.assertEqual(len(result.model.open_questions), 1)
        self.assertEqual(result.model.open_questions[0].question, "What output current is required at 3.3 V?")
        self.assertEqual(next(req for req in initial.requirements if req.id == "REQ_PWR_002").constraint.value, 5)
        self.assertEqual(len(initial.open_questions), 0)

    def test_existing_open_questions_are_preserved_and_new_ids_are_sequential(self):
        initial = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [
                            {
                                "category": "power",
                                "type": "output_voltage",
                                "constraint": {"kind": "nominal", "value": 5, "unit": "V"},
                            }
                        ]
                    )
                ]
            )
        ).interpret_new(message("Make a 5 V converter."), created_at=CREATED_AT).model
        self.assertEqual([question.id for question in initial.open_questions], ["Q_001"])

        next_question = output(
            {
                "operations": [
                    {
                        "operation": "ask_open_question",
                        "question": {
                            "question": "What input voltage should be supported?",
                            "reason": "Input voltage was not provided.",
                            "blocking": True,
                            "importance": "high",
                        },
                    }
                ]
            }
        )
        result = RequirementInterpreter(FakeLLMClient([next_question])).interpret_change(
            message("Also make sure it works from my adapter.", "MSG_002"),
            initial,
            updated_at=UPDATED_AT,
        )

        self.assertEqual([question.id for question in result.model.open_questions], ["Q_001", "Q_002"])
        self.assertEqual([question.id for question in initial.open_questions], ["Q_001"])

    def test_invalid_llm_output_triggers_repair(self):
        valid = extraction(power_supply_requirements())
        fake = FakeLLMClient(["not json", valid])
        interpreter = RequirementInterpreter(fake, max_repair_attempts=2)
        result = interpreter.interpret_new(message("Make a 12V to 5V 2A power supply."))

        self.assertTrue(result.accepted)
        self.assertEqual(len(fake.prompts), 2)
        self.assertIn("previous output was invalid", fake.prompts[1])

    def test_retry_exhaustion_raises_typed_error(self):
        fake = FakeLLMClient(["not json", "still not json", "also not json"])
        interpreter = RequirementInterpreter(fake, max_repair_attempts=2)

        with self.assertRaises(RequirementInterpretationError) as context:
            interpreter.interpret_new(message("Make a 12V to 5V 2A power supply."))

        self.assertEqual(context.exception.message_id, "MSG_001")
        self.assertEqual(context.exception.attempt_count, 3)

    def test_unknown_unit_draft_fails_before_canonical_model(self):
        interpreter = RequirementInterpreter(
            FakeLLMClient(
                [
                    extraction(
                        [
                            {
                                "category": "power",
                                "type": "input_voltage",
                                "constraint": {"kind": "nominal", "value": 12, "unit": "bananas"},
                            }
                        ]
                    )
                ]
            )
        )

        with self.assertRaises(RequirementInterpretationError):
            interpreter.interpret_new(message("Use a weird unit."))


if __name__ == "__main__":
    unittest.main()
