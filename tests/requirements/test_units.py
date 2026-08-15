import unittest

from schematic_ai.domain.requirements.units import UnitNormalizationError, normalize_unit


class UnitNormalizerTests(unittest.TestCase):
    def test_normalizes_known_aliases(self):
        self.assertEqual(normalize_unit("volts"), "V")
        self.assertEqual(normalize_unit("v"), "V")
        self.assertEqual(normalize_unit("amps"), "A")
        self.assertEqual(normalize_unit("milliamps"), "mA")
        self.assertEqual(normalize_unit("celsius"), "degC")
        self.assertEqual(normalize_unit("khz"), "kHz")
        self.assertEqual(normalize_unit("mhz"), "MHz")

    def test_unknown_units_are_rejected(self):
        with self.assertRaises(UnitNormalizationError):
            normalize_unit("bananas")

    def test_blank_units_are_rejected(self):
        with self.assertRaises(UnitNormalizationError):
            normalize_unit("   ")


if __name__ == "__main__":
    unittest.main()
