import math
import unittest

from pydantic import ValidationError

from schematic_ai.domain.requirements.constraints import (
    BooleanConstraint,
    Condition,
    EnumConstraint,
    EnumPreferenceConstraint,
    ExactConstraint,
    MaximumConstraint,
    MinimumConstraint,
    NominalConstraint,
    NominalWithToleranceConstraint,
    Quantity,
    RangeConstraint,
    TextConstraint,
    Tolerance,
)


class ConstraintTests(unittest.TestCase):
    def test_core_constraint_kinds(self):
        self.assertEqual(ExactConstraint(value=5, unit="V").kind, "exact")
        self.assertEqual(NominalConstraint(value=12, unit="V").kind, "nominal")
        self.assertEqual(MinimumConstraint(value=2, unit="A").kind, "minimum")
        self.assertEqual(MaximumConstraint(value=100, unit="mA").kind, "maximum")
        self.assertEqual(BooleanConstraint(value=True).value, True)
        self.assertEqual(EnumConstraint(allowed=["USB-C", "barrel_jack"]).allowed[0], "USB-C")
        self.assertEqual(EnumPreferenceConstraint(preferred=["Texas Instruments"]).preferred[0], "Texas Instruments")
        self.assertEqual(TextConstraint(value="Prefer screw terminals").value, "Prefer screw terminals")

    def test_range_rejects_minimum_above_maximum(self):
        with self.assertRaises(ValidationError):
            RangeConstraint(minimum=16, maximum=9, unit="V")

    def test_quantity_rejects_non_finite_values(self):
        with self.assertRaises(ValidationError):
            Quantity(value=math.inf, unit="A")

    def test_tolerances(self):
        percent = Tolerance(type="percent", minus=2, plus=2)
        self.assertEqual(percent.type, "percent")

        absolute = Tolerance(type="absolute", minus=0.1, plus=0.1, unit="V")
        self.assertEqual(absolute.unit, "V")

        constrained = NominalWithToleranceConstraint(
            nominal=5,
            unit="V",
            tolerance=percent,
        )
        self.assertEqual(constrained.kind, "nominal_with_tolerance")

    def test_invalid_tolerances(self):
        with self.assertRaises(ValidationError):
            Tolerance(type="percent", minus=-1, plus=2)

        with self.assertRaises(ValidationError):
            Tolerance(type="absolute", minus=0.1, plus=0.1)

    def test_conditions(self):
        condition = Condition(
            parameter="load_current",
            constraint={"kind": "range", "minimum": 0, "maximum": 1.5, "unit": "A"},
        )
        self.assertIsInstance(condition.constraint, RangeConstraint)

    def test_enum_constraints_require_options(self):
        with self.assertRaises(ValidationError):
            EnumConstraint(allowed=[])

        with self.assertRaises(ValidationError):
            EnumPreferenceConstraint(preferred=[])

    def test_enum_constraints_reject_duplicate_options(self):
        with self.assertRaises(ValidationError):
            EnumConstraint(allowed=["I2C", "I2C"])

        with self.assertRaises(ValidationError):
            EnumPreferenceConstraint(preferred=["Texas Instruments", "Texas Instruments"])


if __name__ == "__main__":
    unittest.main()
