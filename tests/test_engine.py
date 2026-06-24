import base64
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.audit import QualityAuditEngine
from core.exporter import PDFExporter
from core.generator import DocGenerationEngine, HardwareProfile
from core.document_types import resolve_document_type
from core.drc import DrcRuleEngine
from core.improvement import ImprovementMemory
from core.parser import HardwareManifestParser
from core.plugins import PluginRegistry
from core.skill_rules import SkillRuleEngine


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
            self.assertNotIn("Automated Engineering Delivery", html)
            product_html = PDFExporter(css).convert_markdown_to_html("Product Brief", "# Board A V0.4 Product Brief\n\n## Scope")
            self.assertIn("<title>Board A V0.4 Product Brief</title>", product_html)
            self.assertNotIn("<h2>Board A V0.4 Product Brief</h2>", product_html)
            relaxed = PDFExporter._layout_profile("## Product Visuals\n![Architecture](stacked_architecture.jpeg)")
            compact = PDFExporter._layout_profile("## Scope\nNo visuals")
            self.assertGreater(relaxed["body_size"], compact["body_size"])
            self.assertGreater(relaxed["product_image_height"], compact["product_image_height"])
            unsafe_html = PDFExporter(css).convert_markdown_to_html("Safe", "## Scope\n<script>alert(1)</script>")
            self.assertNotIn("<script>", unsafe_html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", unsafe_html)

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

    def test_local_only_api_key_override_ignores_environment_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts.json"
            prompts.write_text(json.dumps({"user_manual": "Prompt"}), encoding="utf-8")
            old_key = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "should-not-be-used"
            try:
                engine = DocGenerationEngine(prompts_path=prompts, api_key="")
                self.assertEqual(engine.api_key, "")
                draft = engine.generate_document(
                    "user_manual",
                    {"detected_pins": [], "peripherals": [], "schematics": [], "pcb": [], "metadata": {}},
                )
            finally:
                if old_key is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = old_key

            self.assertIn("User Manual", draft)

    def test_product_brief_extracts_visuals_and_easyeda_ports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prompts = root / "prompts.json"
            prompts.write_text(json.dumps({"user_manual": "Prompt", "product_brief": "Prompt"}), encoding="utf-8")
            schematic_dir = root / "schematics"
            pcb_dir = root / "pcb"
            schematic_dir.mkdir()
            pcb_dir.mkdir()
            tiny_png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
            )
            (pcb_dir / "board.png").write_bytes(tiny_png)
            (pcb_dir / "advanced_ev_charging_control.jpeg").write_bytes(tiny_png)
            (pcb_dir / "stacked_architecture.jpeg").write_bytes(tiny_png)
            epru = "\n".join(
                [
                    '{"type":"DOCHEAD","ticket":1}||{"docType":"SCH_PAGE","uuid":"p1"}|',
                    '{"type":"META","ticket":2,"id":"META"}||{"title":"JTAG-RESET"}|',
                    '{"type":"COMPONENT","ticket":3,"id":"c1"}||{"partId":"CONN-TH_14P","x":0,"y":0,"attrs":[]}|',
                    '{"type":"ATTR","ticket":4,"id":"a1"}||{"parentId":"c1","key":"Designator","value":"CN1"}|',
                    '{"type":"ATTR","ticket":5,"id":"a2"}||{"parentId":"c1","key":"Manufacturer Part","value":"DSP_JTAG"}|',
                    '{"type":"COMPONENT","ticket":6,"id":"s1"}||{"partId":"pid","x":0,"y":0,"attrs":[]}|',
                    '{"type":"ATTR","ticket":7,"id":"a3"}||{"parentId":"s1","key":"Designator","value":"JTAG_TCK"}|',
                    '{"type":"COMPONENT","ticket":8,"id":"s2"}||{"partId":"pid","x":0,"y":0,"attrs":[]}|',
                    '{"type":"ATTR","ticket":9,"id":"a4"}||{"parentId":"s2","key":"Designator","value":"RESET"}|',
                ]
            )
            with zipfile.ZipFile(pcb_dir / "board.epro2", "w") as archive:
                archive.writestr("project2.json", "{}")
                archive.writestr("LIB_TEST.epru", epru)

            profile = HardwareManifestParser(root / "code", schematic_dir, pcb_dir).compile_hardware_profile()
            analysis = DocGenerationEngine._collect_analysis(HardwareProfile.model_validate(profile))
            draft = DocGenerationEngine(prompts_path=prompts, api_key="").generate_document("product_brief", profile)

            self.assertEqual(analysis["board_visuals"][0]["width"], "1")
            self.assertEqual(analysis["board_visuals"][0]["height"], "1")
            self.assertEqual(analysis["product_visuals"][0]["visual_kind"], "feature_overview")
            self.assertEqual(analysis["port_map"][0]["port"], "CN1")
            self.assertIn("Product Visuals", draft)
            self.assertIn("Visual Evidence Summary", draft)
            self.assertIn("Working Explanation", draft)
            self.assertIn("Stacked Board Architecture", draft)
            self.assertIn("Upper Board Detail", draft)
            self.assertIn("Lower Board Detail", draft)
            self.assertIn("How The Boards Stack Together", draft)
            self.assertIn("Signal Flow Through The Stack", draft)
            self.assertIn("Stacked Bring-Up Sequence", draft)
            self.assertIn("Connector Overview", draft)
            self.assertIn("Firmware loading", draft)
            self.assertIn("![Advanced EV charging control feature overview]", draft)

    def test_drc_report_hides_reconciled_source_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts.json"
            prompts.write_text(json.dumps({"user_manual": "Prompt", "drc_report": "Prompt"}), encoding="utf-8")
            engine = DocGenerationEngine(prompts_path=prompts, api_key="")

            draft = engine.generate_document(
                "drc_report",
                {
                    "detected_pins": [],
                    "peripherals": [],
                    "schematics": [
                        {
                            "source_file": "sheet_1.pdf",
                            "page_count": 1,
                            "analysis": {
                                "power_rails": [{"net": "3V3", "role": "Logic rail"}],
                                "interface_groups": [{"name": "USB", "evidence": ["USB"], "confidence": 80}],
                                "drc_findings": [
                                    {
                                        "id": "DRC-DBG-001",
                                        "severity": "minor",
                                        "domain": "Debug",
                                        "check": "Debug access",
                                        "finding": "ICs were detected but no clear debug/programming block was found.",
                                    }
                                ],
                                "readiness_score": 85,
                            },
                        },
                        {
                            "source_file": "sheet_2.pdf",
                            "page_count": 1,
                            "analysis": {
                                "interface_groups": [
                                    {"name": "Debug/Programming", "evidence": ["SWD", "RESET"], "confidence": 80}
                                ],
                                "readiness_score": 85,
                            },
                        },
                    ],
                    "pcb": [],
                    "metadata": {"schematic_files_scanned": 2, "pcb_files_scanned": 0, "code_files_scanned": 0},
                },
            )

            self.assertIn("Evidence Coverage Matrix", draft)
            self.assertNotIn("DRC-DBG-001", draft)

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
                                "optimization_actions": [
                                    {
                                        "priority": "P1",
                                        "area": "Wireless readiness",
                                        "recommendation": "Add modem release gate.",
                                        "why": "Improves field readiness.",
                                        "evidence": "SIM",
                                    }
                                ],
                                "validation_matrix": [
                                    {
                                        "subsystem": "Wireless/SIM",
                                        "objective": "Confirm modem path",
                                        "method": "Check power, SIM, UART, and antenna.",
                                        "acceptance": "Module responds.",
                                    }
                                ],
                                "bringup_sequence": ["Verify base rails before modem testing."],
                                "skill_review_gates": [
                                    {
                                        "id": "wireless-rf-certification",
                                        "title": "Wireless/RF Certification Gate",
                                        "priority": "P1",
                                        "domain": "RF/Wireless",
                                        "source_skill": "component-iot-rf-wireless",
                                        "objective": "Confirm radio evidence.",
                                        "checklist": ["Confirm antenna and SIM evidence."],
                                        "evidence": "groups: Wireless/SIM",
                                    }
                                ],
                                "readiness_score": 74,
                            },
                        }
                    ],
                    "pcb": [],
                    "metadata": {"schematic_files_scanned": 1},
                },
            )

            self.assertIn("Detailed System Overview", draft)
            self.assertIn("Professional Functional Block Guide", draft)
            self.assertIn("How it works", draft)
            self.assertIn("Power Input, Rail Checks, And Bring-Up", draft)
            self.assertIn("Interface Operation Guide", draft)
            self.assertIn("Subsystem Service Notes", draft)
            self.assertIn("Troubleshooting Matrix", draft)
            self.assertIn("Professional Validation Matrix", draft)
            self.assertIn("200 Percent Optimization Roadmap", draft)
            self.assertIn("Integrated Schematic And PCB Skill Pack", draft)
            self.assertIn("Wireless/RF Certification Gate", draft)
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
        self.assertTrue(analysis["drc_findings"])
        self.assertTrue(analysis["risk_flags"])
        self.assertTrue(analysis["optimization_actions"])
        self.assertTrue(analysis["validation_matrix"])
        self.assertTrue(analysis["bringup_sequence"])
        self.assertTrue(analysis["skill_review_gates"])
        gate_titles = {gate["title"] for gate in analysis["skill_review_gates"]}
        self.assertIn("Signal Integrity Gate", gate_titles)
        self.assertIn("Power Integrity And PDN Gate", gate_titles)
        self.assertGreater(analysis["readiness_score"], 0)

    def test_skill_rule_engine_triggers_review_gates(self) -> None:
        engine = SkillRuleEngine()
        gates = engine.build_review_gates(
            "USB HDMI PCIE 3V3 VBAT TVS SIM ANTENNA",
            [{"net": "3V3", "role": "3.3 V logic rail"}],
            [{"name": "USB"}, {"name": "Wireless/SIM"}, {"name": "Protection/ESD"}],
            {"integrated_circuits": 2, "connectors_headers": 1},
            [{"reference": "U1", "value_or_part": "MCU"}],
            ["High-speed differential routing requires impedance review."],
        )

        titles = {gate["title"] for gate in gates}

        self.assertIn("Signal Integrity Gate", titles)
        self.assertIn("Wireless/RF Certification Gate", titles)
        self.assertIn("Supply Chain And BOM Gate", titles)
        self.assertTrue(SkillRuleEngine.summarize_gates(gates)["gate_count"])

    def test_document_type_resolver_allows_fumbles(self) -> None:
        self.assertEqual(resolve_document_type("manual"), "user_manual")
        self.assertEqual(resolve_document_type("test"), "test_report")
        self.assertEqual(resolve_document_type("drc"), "drc_report")
        self.assertEqual(resolve_document_type("electrical rule check"), "drc_report")
        self.assertEqual(resolve_document_type("full package"), "all")
        self.assertEqual(resolve_document_type("compliance-brief"), "compliance_brief")

    def test_drc_report_includes_boundary_and_rule_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts.json"
            prompts.write_text(json.dumps({"user_manual": "Prompt"}), encoding="utf-8")
            engine = DocGenerationEngine(prompts_path=prompts, api_key="")
            draft = engine.generate_document(
                "drc_report",
                {
                    "detected_pins": [],
                    "peripherals": [],
                    "schematics": [
                        {
                            "source_file": "board.pdf",
                            "page_count": 2,
                            "analysis": {
                                "readiness_score": 82,
                                "power_rails": [{"net": "3V3", "role": "3.3 V logic rail"}],
                                "interface_groups": [{"name": "USB", "evidence": ["USB"], "confidence": 80}],
                                "risk_flags": ["High-speed differential routing requires impedance review."],
                                "skill_review_gates": [{"priority": "P1", "title": "Signal Integrity Gate", "evidence": "USB"}],
                            },
                        }
                    ],
                    "pcb": [],
                    "metadata": {"schematic_files_scanned": 1, "code_files_scanned": 0, "pcb_files_scanned": 0},
                },
            )

            self.assertIn("Schematic DRC/ERC Review", draft)
            self.assertIn("DRC Capability Boundary", draft)
            self.assertIn("Open DRC Findings", draft)
        self.assertIn("Native DRC/ERC Upgrade Path", draft)

    def test_drc_rule_engine_flags_high_speed_and_fieldbus_evidence(self) -> None:
        findings = DrcRuleEngine().build_findings(
            "USB D+ D- VBUS RS485 A1 B1 CANH CANL 3V3 5V GND U1 MCU",
            ["GND", "3V3", "5V"],
            [{"net": "3V3", "role": "3.3 V logic rail"}, {"net": "5V", "role": "5 V rail"}],
            [{"name": "USB"}, {"name": "RS485"}, {"name": "CAN/Fieldbus"}],
            {"integrated_circuits": 1, "capacitors": 0, "inductors": 0},
            [{"reference": "U1", "value_or_part": "MCU"}],
            [],
        )
        ids = {finding["id"] for finding in findings}

        self.assertIn("DRC-SI-010", ids)
        self.assertIn("DRC-FIELD-010", ids)
        self.assertIn("DRC-FIELD-020", ids)

    def test_drc_reconciliation_suppresses_cross_sheet_false_positive(self) -> None:
        findings = [
            {
                "id": "DRC-DBG-001",
                "severity": "minor",
                "domain": "Debug",
                "finding": "ICs were detected but no clear debug/programming block was found.",
            },
            {
                "id": "DRC-SI-010",
                "severity": "major",
                "domain": "Signal Integrity",
                "finding": "High-speed layout evidence is missing.",
            },
        ]
        reconciled = DrcRuleEngine.reconcile_findings(
            findings,
            [{"name": "Debug/Programming"}, {"name": "USB"}],
            [{"net": "3V3"}],
            {"pcb_files_scanned": 1},
        )
        ids = {finding["id"] for finding in reconciled}

        self.assertNotIn("DRC-DBG-001", ids)
        self.assertIn("DRC-SI-010", ids)

    def test_improvement_memory_records_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = ImprovementMemory(Path(temp_dir) / "memory.json")
            summary = memory.record_generation(
                {
                    "schematics": [
                        {
                            "analysis": {
                                "readiness_score": 81,
                                "risk_flags": ["High-speed differential routing requires review."],
                                "skill_review_gates": [{"title": "Signal Integrity Gate"}],
                                "interface_groups": [{"name": "USB"}],
                                "power_rails": [{"net": "3V3"}],
                            }
                        }
                    ],
                    "pcb": [],
                    "metadata": {"code_files_scanned": 0, "pcb_files_scanned": 0},
                },
                ["user_manual"],
                [Path("user_manual.pdf")],
            )

            self.assertEqual(summary["runs_total"], 1)
            self.assertEqual(summary["average_readiness_score"], 81)
            self.assertTrue(summary["adaptive_hints"])
            self.assertTrue(summary["recurring_gaps"])

    def test_quality_audit_flags_missing_release_evidence(self) -> None:
        audit = QualityAuditEngine().build_audit(
            {"metadata": {"schematic_files_scanned": 1, "code_files_scanned": 0, "pcb_files_scanned": 0}},
            {
                "readiness_score": 82,
                "power_rails": [{"net": "3V3"}],
                "interface_groups": [{"name": "USB"}],
                "risk_flags": ["High-speed differential routing requires impedance review."],
                "skill_review_gates": [{"priority": "P1", "title": "Signal Integrity Gate"}],
            },
        )

        self.assertEqual(audit["release_status"], "Engineering review required")
        self.assertGreaterEqual(audit["counts"]["major"], 2)
        self.assertTrue(audit["next_actions"])

    def test_plugin_registry_builds_internet_research_pack(self) -> None:
        catalog = PluginRegistry().build_catalog(
            {"schematics": [], "pcb": [], "metadata": {}},
            {
                "key_parts": [{"reference": "U1", "value_or_part": "STM32F407VGT6"}],
                "interface_groups": [{"name": "USB"}],
                "skill_review_gates": [{"title": "Signal Integrity Gate"}],
            },
        )

        self.assertGreaterEqual(catalog["summary"]["total"], 5)
        self.assertGreater(catalog["summary"]["internet_enabled"], 0)
        part_links = catalog["research_pack"]["parts"][0]["links"]
        self.assertTrue(any("digikey.com" in link["url"] for link in part_links))
        self.assertTrue(any(plugin["id"] == "kicad_cli" for plugin in catalog["plugins"]))


if __name__ == "__main__":
    unittest.main()
