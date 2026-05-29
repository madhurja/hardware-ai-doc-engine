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

    def test_user_manual_includes_detailed_operator_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts.json"
            prompts.write_text(json.dumps({"user_manual": "Prompt"}), encoding="utf-8")
            engine = DocGenerationEngine(prompts_path=prompts, api_key="")

            draft = engine.generate_document(
                "user_manual",
                {
                    "detected_pins": [],
                    "peripherals": [],
                    "schematics": [
                        {
                            "source_file": "cm4.pdf",
                            "page_count": 1,
                            "analysis": {
                                "power_rails": [
                                    {"net": "CM4_5V", "role": "5 V input/distribution rail"},
                                    {"net": "VBAT", "role": "Battery or modem supply"},
                                ],
                                "interface_groups": [
                                    {"name": "USB", "evidence": ["USB"], "confidence": 80},
                                    {"name": "Wireless/SIM", "evidence": ["SIM"], "confidence": 80},
                                ],
                                "key_parts": [{"reference": "SIMCOM1", "value_or_part": "SIM-M2"}],
                                "test_focus": ["SIM/LTE modem power, UART, USB, reset, and enable-line verification"],
                                "risk_flags": ["Wireless/SIM section requires RF evidence before release."],
                            },
                        }
                    ],
                    "pcb": [],
                    "metadata": {"schematic_files_scanned": 1},
                },
            )

            self.assertIn("Detailed System Overview", draft)
            self.assertIn("Power Input, Rail Checks, And Bring-Up", draft)
            self.assertIn("Interface Operation Guide", draft)
            self.assertIn("Troubleshooting Matrix", draft)
            self.assertIn("SIMCOM1", draft)

    def test_parser_extracts_schematic_tokens_from_text(self) -> None:
        text = "U156 LM5164QDDARQ1 GND VIN +12V 3V3 MCU_HV_FB1 R192 10K C133 2.2uF SIMCOM1 SIM-M2"

        components = HardwareManifestParser._extract_component_tokens(text)
        nets = HardwareManifestParser._extract_net_tokens(text)

        self.assertIn({"reference": "U156", "value_or_part": "LM5164QDDARQ1"}, components)
        self.assertIn({"reference": "SIMCOM1", "value_or_part": "SIM-M2"}, components)
        self.assertIn("MCU_HV_FB1", nets)
        self.assertIn("+12V", nets)

    def test_schematic_analysis_classifies_cm4_interfaces(self) -> None:
        text = """
        CM4_5V CM4_3V3 CM4_1V8 VBAT USB0_P USB0_N HDMI0_SDA HDMI0_SCL PCIE_RX_P SD_PWR_ON75 1.8V
        TRD0_P TRD0_N RJ1 SIMCOM1 SIM1_VCC GNSS_Enbale RS485 SP3485 U14 SMAJ12CA
        U5 FE1_1S U9 PCF85063ATL FAN EMC2301 GPIO2 GPIO3 TPD4EUSB30
        """

        analysis = HardwareManifestParser._analyze_schematic_text(text)
        groups = {group["name"] for group in analysis["interface_groups"]}
        rails = {rail["net"] for rail in analysis["power_rails"]}

        self.assertIn("USB", groups)
        self.assertIn("Wireless/SIM", groups)
        self.assertIn("RS485", groups)
        self.assertIn("CM4_5V", rails)
        self.assertNotIn("SD_PWR_ON75", rails)
        self.assertNotIn("8V", rails)
        self.assertTrue(analysis["risk_flags"])


if __name__ == "__main__":
    unittest.main()
