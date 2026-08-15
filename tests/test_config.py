import os
import unittest
from unittest.mock import patch

from schematic_ai.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_defaults_to_ollama_qwen_coder(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()

        self.assertEqual(settings.llm_provider, "ollama")
        self.assertEqual(settings.ollama_model_name, "qwen-coder")
        self.assertIsNone(settings.kicad9_footprint_dir)
        self.assertIsNone(settings.kicad9_symbol_dir)

    def test_reads_kicad9_global_variables(self):
        with patch.dict(
            os.environ,
            {
                "KICAD9_FOOTPRINT_DIR": "C:/KiCad/9.0/share/kicad/footprints",
                "KICAD9_SYMBOL_DIR": "C:/KiCad/9.0/share/kicad/symbols",
                "OLLAMA_MODEL_NAME": "qwen-coder",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.kicad9_footprint_dir, "C:/KiCad/9.0/share/kicad/footprints")
        self.assertEqual(settings.kicad9_symbol_dir, "C:/KiCad/9.0/share/kicad/symbols")
        self.assertEqual(settings.ollama_model_name, "qwen-coder")


if __name__ == "__main__":
    unittest.main()

