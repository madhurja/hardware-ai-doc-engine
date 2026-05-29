import json
import os
import tempfile
import unittest
from pathlib import Path

from core.exporter import PDFExporter
from core.generator import DocGenerationEngine
from core.parser import HardwareManifestParser


class EngineTests(unittest.TestCase):
    def test_parser_detects_pins_and_peripherals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code_dir = root / "code"
            schematic_dir = root / "schematics"
            pcb_dir = root / "pcb"
            code_dir.mkdir()
            schematic_dir.mkdir()
            pcb_dir.mkdir()

            (code_dir / "main.ino").write_text(
                "\n".join(
                    [
                        "#define LED_STATUS GPIO_PIN_13",
                        "#define RELAY_PIN PA_5",
                        "Serial.begin(115200);",
                        "SPI.begin();",
                        "Wire.begin();",
                    ]
                ),
                encoding="utf-8",
            )
            (pcb_dir / "bom.csv").write_text("part,quantity\nMCU,1\nLED,2\n", encoding="utf-8")

            profile = HardwareManifestParser(code_dir, schematic_dir, pcb_dir).compile_hardware_profile()

            self.assertEqual(profile["metadata"]["pin_count"], 2)
            self.assertEqual(profile["metadata"]["peripheral_count"], 3)
            self.assertEqual(profile["detected_pins"][0]["signal_name"], "LED_STATUS")
            self.assertEqual(profile["pcb"][0]["row"]["part"], "MCU")

    def test_exporter_builds_semantic_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            css = Path(temp_dir) / "base.css"
            css.write_text("body { font-family: Arial; }", encoding="utf-8")

            html = PDFExporter(css).convert_markdown_to_html("Test Report", "## Scope\n- Item one")

            self.assertIn("<title>Test Report</title>", html)
            self.assertIn("<h2>Scope</h2>", html)
            self.assertIn("<li>Item one</li>", html)

    def test_generator_without_api_key_returns_local_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts.json"
            prompts.write_text(json.dumps({"user_manual": "Prompt"}), encoding="utf-8")
            old_key = os.environ.pop("OPENAI_API_KEY", None)
            try:
                engine = DocGenerationEngine(prompts_path=prompts, api_key="")
                draft = engine.generate_document(
                    "user_manual",
                    {
                        "detected_pins": [{"signal_name": "LED", "physical_pin": "13", "source_file": "main.c"}],
                        "peripherals": [],
                        "schematics": [],
                        "pcb": [],
                        "metadata": {"code_files_scanned": 1},
                    },
                )
            finally:
                if old_key is not None:
                    os.environ["OPENAI_API_KEY"] = old_key

            self.assertIn("User Manual", draft)
            self.assertIn("LED", draft)

    def test_parser_extracts_schematic_tokens_from_text(self) -> None:
        text = "U156 LM5164QDDARQ1 GND VIN +12V 3V3 MCU_HV_FB1 R192 10K C133 2.2uF"

        components = HardwareManifestParser._extract_component_tokens(text)
        nets = HardwareManifestParser._extract_net_tokens(text)

        self.assertIn({"reference": "U156", "value_or_part": "LM5164QDDARQ1"}, components)
        self.assertIn("MCU_HV_FB1", nets)
        self.assertIn("+12V", nets)


if __name__ == "__main__":
    unittest.main()
