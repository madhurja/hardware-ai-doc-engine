from __future__ import annotations

import csv
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.skill_rules import SkillRuleEngine


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectedPin:
    signal_name: str
    physical_pin: str
    source_file: str
    line_number: int


@dataclass(frozen=True)
class DetectedPeripheral:
    name: str
    configuration: str
    source_file: str
    line_number: int


class HardwareManifestParser:
    """Builds a structured hardware profile from local firmware and manifests."""

    CODE_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".ino"}
    MANIFEST_EXTENSIONS = {".csv", ".tsv", ".json", ".xml", ".net", ".pdf"}
    MAX_SCAN_FILES = 250
    MAX_SCAN_BYTES = 100 * 1024 * 1024

    PIN_PATTERN = re.compile(r"#define\s+(\w+)\s+(GPIO_PIN_\d+|PA_\d+|PB_\d+|\d+)")
    SERIAL_PATTERN = re.compile(r"\bSerial(?:\d*)\.begin\((\d+)\)")
    SPI_PATTERN = re.compile(r"\bSPI\.begin\(\)")
    I2C_PATTERN = re.compile(r"\bWire\.begin\(([^)]*)\)")
    INTERFACE_PATTERNS = {
        "Power": ("CM4_5V", "+5V", "5V", "3V3", "1V8", "VBAT", "PWR_3V3", "VDD_3V3", "VDD_1V8", "12V"),
        "Ethernet": ("ETH", "TRD", "RJ45", "MDI", "Ethernet"),
        "USB": ("USB", "USBD", "VBUS", "DATA+", "DATA-", "D+", "D-"),
        "HDMI": ("HDMI", "HOTPLUG", "CEC"),
        "Camera/Display": ("CAM", "DSI", "CSI"),
        "PCIe": ("PCIE", "PCIe", "PET", "PER", "CLKREQ"),
        "GPIO Header": ("GPIO", "Raspberry 40 PIN", "WPiBCM", "ID_SCL", "ID_SDA"),
        "SD/eMMC": ("SD_", "SDIO", "DAT0", "DAT1", "DAT2", "DAT3"),
        "I2C": ("SCL", "SDA", "I2C"),
        "UART": ("UART", "TXD", "RXD", "P_TX", "P_RX"),
        "SPI": ("SPI", "MOSI", "MISO", "SCLK", "SPI_CS", "CS0", "CS1"),
        "CAN/Fieldbus": ("CANH", "CANL", "CAN_TX", "CAN_RX", "TJA105", "SN65HVD"),
        "Audio/I2S": ("I2S", "PCM", "BCLK", "LRCLK", "MCLK", "DIN", "DOUT"),
        "Debug/Programming": ("JTAG", "SWD", "BOOT", "RUN", "RESET", "GLOBAL_EN", "nRPIBOOT"),
        "Wireless/SIM": ("SIM", "UIM", "SIMCOM", "GNSS", "FlightMode", "FightMode", "W_DISABLE", "LTE"),
        "RTC": ("RTC", "PCF85063", "CR2032", "32.768K"),
        "Fan": ("FAN", "TACH", "EMC2301"),
        "RS485": ("RS485", "SP3485", "SMAJ", "A1", "B1"),
        "LED Indicators": ("LED", "STA", "NET_LED", "PI_PWR_LED"),
        "WiFi/Bluetooth Control": ("WIFI_EN", "BT_EN", "WiFi", "BT_nDisable"),
        "Regulators/Power Control": ("TPS", "MP1476", "LM5164", "REG_", "LDO", "DCDC", "DC/DC", "PWR_EN", "ENABLE", "PGOOD"),
        "Protection/ESD": ("TVS", "SMBJ", "SMAJ", "TPD4EUSB30", "SMF05C", "B5819"),
    }
    COMPONENT_FAMILIES = {
        "integrated_circuits": re.compile(r"\bU\d{1,4}\b"),
        "connectors_headers": re.compile(r"\b(?:J|JP|H|P|RJ|USB|HDMI)\d{1,4}\b"),
        "resistors": re.compile(r"\bR\d{1,4}\b"),
        "capacitors": re.compile(r"\bC\d{1,4}\b"),
        "inductors": re.compile(r"\bL\d{1,4}\b"),
        "diodes_tvs_leds": re.compile(r"\b(?:D|LED|TVS)\d{1,4}\b"),
        "transistors_switches": re.compile(r"\b(?:Q|S)\d{1,4}\b"),
        "crystals": re.compile(r"\bY\d{1,4}\b"),
    }

    def __init__(
        self,
        code_dir: str | Path = "input_drop/code",
        schematic_dir: str | Path = "input_drop/schematics",
        pcb_dir: str | Path = "input_drop/pcb",
    ) -> None:
        self.code_dir = Path(code_dir)
        self.schematic_dir = Path(schematic_dir)
        self.pcb_dir = Path(pcb_dir)

    def compile_hardware_profile(self) -> dict[str, Any]:
        code_files = self._list_files(self.code_dir, self.CODE_EXTENSIONS)
        schematic_files = self._list_files(self.schematic_dir, self.MANIFEST_EXTENSIONS)
        pcb_files = self._list_files(self.pcb_dir, self.MANIFEST_EXTENSIONS)

        if not code_files and not schematic_files and not pcb_files:
            LOGGER.warning("No source files were found in input_drop folders.")

        detected_pins, peripherals = self._scan_code_files(code_files)
        schematic_parts = self._scan_manifest_files(schematic_files)
        pcb_parts = self._scan_manifest_files(pcb_files)

        return {
            "detected_pins": [asdict(pin) for pin in detected_pins],
            "peripherals": [asdict(peripheral) for peripheral in peripherals],
            "schematics": schematic_parts,
            "pcb": pcb_parts,
            "metadata": {
                "code_files_scanned": len(code_files),
                "schematic_files_scanned": len(schematic_files),
                "pcb_files_scanned": len(pcb_files),
                "pin_count": len(detected_pins),
                "peripheral_count": len(peripherals),
            },
        }

    def _scan_code_files(
        self,
        files: list[Path],
    ) -> tuple[list[DetectedPin], list[DetectedPeripheral]]:
        detected_pins: list[DetectedPin] = []
        peripherals: list[DetectedPeripheral] = []

        for path in files:
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line_number, line in enumerate(handle, 1):
                        pin_match = self.PIN_PATTERN.search(line)
                        if pin_match:
                            detected_pins.append(
                                DetectedPin(
                                    signal_name=pin_match.group(1),
                                    physical_pin=pin_match.group(2),
                                    source_file=str(path),
                                    line_number=line_number,
                                )
                            )

                        for peripheral in self._detect_peripherals(line, path, line_number):
                            peripherals.append(peripheral)
            except OSError as exc:
                LOGGER.warning("Could not read source file %s: %s", path, exc)

        return detected_pins, peripherals

    def _detect_peripherals(
        self,
        line: str,
        path: Path,
        line_number: int,
    ) -> list[DetectedPeripheral]:
        peripherals: list[DetectedPeripheral] = []

        serial_match = self.SERIAL_PATTERN.search(line)
        if serial_match:
            peripherals.append(
                DetectedPeripheral("Serial", f"baud={serial_match.group(1)}", str(path), line_number)
            )

        if self.SPI_PATTERN.search(line):
            peripherals.append(DetectedPeripheral("SPI", "begin()", str(path), line_number))

        i2c_match = self.I2C_PATTERN.search(line)
        if i2c_match:
            config = i2c_match.group(1).strip() or "default"
            peripherals.append(DetectedPeripheral("I2C", config, str(path), line_number))

        return peripherals

    def _scan_manifest_files(self, files: list[Path]) -> list[dict[str, Any]]:
        manifests: list[dict[str, Any]] = []
        for path in files:
            try:
                if path.suffix.lower() in {".csv", ".tsv"}:
                    manifests.extend(self._read_table_manifest(path))
                elif path.suffix.lower() == ".json":
                    manifests.append({"source_file": str(path), "data": json.loads(path.read_text(encoding="utf-8"))})
                elif path.suffix.lower() == ".pdf":
                    manifests.append(self._read_pdf_manifest(path))
                else:
                    manifests.append(self._read_xml_like_manifest(path))
            except (OSError, json.JSONDecodeError, ET.ParseError, UnicodeDecodeError) as exc:
                LOGGER.warning("Could not parse manifest %s: %s", path, exc)
        return manifests

    def _read_table_manifest(self, path: Path) -> list[dict[str, Any]]:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            for row in reader:
                rows.append({"source_file": str(path), "row": {key: value for key, value in row.items() if key}})
        return rows

    def _read_xml_like_manifest(self, path: Path) -> dict[str, Any]:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
        components = []
        for element in root.iter():
            attributes = dict(element.attrib)
            if attributes:
                components.append({"tag": self._strip_namespace(element.tag), "attributes": attributes})
        return {"source_file": str(path), "components": components[:250]}

    def _read_pdf_manifest(self, path: Path) -> dict[str, Any]:
        try:
            import pypdf
        except ImportError as exc:
            raise RuntimeError("PDF ingestion requires pypdf. Install project requirements first.") from exc

        reader = pypdf.PdfReader(str(path))
        pages: list[dict[str, Any]] = []
        all_text: list[str] = []
        for index, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            all_text.append(text)
            pages.append(
                {
                    "page": index,
                    "title": self._infer_page_title(text, index),
                    "text_excerpt": self._compact_text(text, 1200),
                }
            )

        combined_text = "\n".join(all_text)
        return {
            "source_file": str(path),
            "page_count": len(reader.pages),
            "pages": pages,
            "detected_components": self._extract_component_tokens(combined_text),
            "detected_nets": self._extract_net_tokens(combined_text),
            "analysis": self._analyze_schematic_text(combined_text),
            "document_dates": self._extract_document_dates(combined_text),
        }

    @staticmethod
    def _infer_page_title(text: str, index: int) -> str:
        match = re.search(r"Page\s+\d+[_\s-]+([A-Za-z0-9_+/\-\s]+)", text)
        if match:
            return match.group(1).strip()[:80]
        board_match = re.search(r"Board\s+([A-Za-z0-9_+/\-\s]+)", text)
        if board_match:
            return board_match.group(1).strip()[:80]
        return f"Page {index}"

    @staticmethod
    def _extract_component_tokens(text: str) -> list[dict[str, str]]:
        token_pattern = re.compile(
            r"\b((?:USB|HDMI|RJ|LED|TVS|SIMCOM|SIM_CARD)\d{1,4}|[URCLDQJPHSTY][A-Z]?\d{1,4}[A-Z]?)\b"
        )
        value_pattern = re.compile(
            r"\b(\d+(?:\.\d+)?\s?(?:uF|nF|pF|K|k|R|ohm|uH|V|A)|[A-Z0-9-]{4,})\b",
            re.IGNORECASE,
        )
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        components: list[dict[str, str]] = []
        seen: set[str] = set()
        for idx, line in enumerate(lines):
            for match in token_pattern.finditer(line):
                token = match.group(1)
                if token in seen or HardwareManifestParser._looks_like_signal_token(token):
                    continue
                context = (line[match.end() :] + " " + " ".join(lines[idx + 1 : idx + 3])).strip()
                value_match = value_pattern.search(context)
                components.append(
                    {
                        "reference": token,
                        "value_or_part": value_match.group(1) if value_match else "not provided",
                    }
                )
                seen.add(token)
        return components[:300]

    @classmethod
    def _analyze_schematic_text(cls, text: str) -> dict[str, Any]:
        compact_text = cls._compact_text(text, 50000)
        nets = cls._extract_net_tokens(text)
        components = cls._extract_component_tokens(text)
        power_rails = cls._classify_power_rails(nets)
        interface_groups = cls._detect_interface_groups(compact_text)
        component_counts = cls._count_component_families(text)
        key_parts = cls._extract_key_parts(components)
        test_focus = cls._build_test_focus(compact_text, nets)
        risk_flags = cls._build_risk_flags(compact_text, nets)
        optimization_actions = cls._build_optimization_actions(
            compact_text,
            power_rails,
            interface_groups,
            component_counts,
            risk_flags,
        )
        validation_matrix = cls._build_validation_matrix(interface_groups, power_rails)
        bringup_sequence = cls._build_bringup_sequence(power_rails, interface_groups)
        skill_review_gates = SkillRuleEngine().build_review_gates(
            compact_text,
            power_rails,
            interface_groups,
            component_counts,
            key_parts,
            risk_flags,
        )
        return {
            "power_rails": power_rails,
            "interface_groups": interface_groups,
            "component_counts": component_counts,
            "key_parts": key_parts,
            "test_focus": test_focus,
            "risk_flags": risk_flags,
            "optimization_actions": optimization_actions,
            "validation_matrix": validation_matrix,
            "bringup_sequence": bringup_sequence,
            "skill_review_gates": skill_review_gates,
            "skill_pack_summary": SkillRuleEngine.summarize_gates(skill_review_gates),
            "readiness_score": cls._calculate_readiness_score(
                power_rails,
                interface_groups,
                key_parts,
                risk_flags,
                validation_matrix,
                skill_review_gates,
            ),
        }

    @staticmethod
    def _classify_power_rails(nets: list[str]) -> list[dict[str, str]]:
        rails: list[dict[str, str]] = []
        seen: set[str] = set()
        named_fragments = {
            "CM4_5V",
            "CM4_3V3",
            "CM4_1V8",
            "PWR_3V3",
            "VDD_3V3",
            "VDD_1V8",
            "HUB_3V3",
            "HUB_1V8",
            "HDMI_5V",
            "FAN_VCC",
            "VBAT",
        }
        voltage_pattern = re.compile(r"^\+?(?:1V2|1V8|3V|3V3|4V2|5V|12V|24V)$", re.IGNORECASE)
        for net in nets:
            normalized = net.upper().replace(".", "")
            is_voltage = bool(voltage_pattern.fullmatch(normalized))
            is_named_rail = normalized in named_fragments
            if not (is_voltage or is_named_rail) or normalized in seen:
                continue
            role = "Power rail"
            if "VBAT" in normalized:
                role = "Battery or modem supply"
            elif "1V8" in normalized:
                role = "Low-voltage logic rail"
            elif "3V3" in normalized:
                role = "3.3 V logic rail"
            elif "5V" in normalized:
                role = "5 V input/distribution rail"
            elif "12V" in normalized:
                role = "12 V auxiliary rail"
            rails.append({"net": net, "role": role})
            seen.add(normalized)
        return rails[:30]

    @classmethod
    def _detect_interface_groups(cls, text: str) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for name, patterns in cls.INTERFACE_PATTERNS.items():
            hits = sorted({pattern for pattern in patterns if pattern.lower() in text.lower()})
            if hits:
                groups.append({"name": name, "evidence": hits[:8], "confidence": min(100, 35 + len(hits) * 15)})
        return sorted(groups, key=lambda item: (-item["confidence"], item["name"]))

    @classmethod
    def _count_component_families(cls, text: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for family, pattern in cls.COMPONENT_FAMILIES.items():
            counts[family] = len(set(pattern.findall(text)))
        return counts

    @staticmethod
    def _extract_key_parts(components: list[dict[str, str]]) -> list[dict[str, str]]:
        generic_values = {"not provided", "10K", "100K", "0R", "104", "100nF", "10uF", "22pF", "1K", "GND"}
        key_reference_pattern = re.compile(r"^(?:U\d|SIMCOM\d|RJ\d|USB\d|HDMI\d|H\d|J\d)")
        key_parts = []
        for component in components:
            reference = component.get("reference", "")
            value = component.get("value_or_part", "")
            if (
                key_reference_pattern.search(reference)
                and value
                and value not in generic_values
                and re.search(r"[A-Z]{2,}|\d{3,}", value)
            ):
                key_parts.append(component)
        return key_parts[:40]

    @classmethod
    def _build_test_focus(cls, text: str, nets: list[str]) -> list[str]:
        focus = []
        rail_names = [rail["net"] for rail in cls._classify_power_rails(nets)[:8]]
        if rail_names:
            focus.append("Power-up sequencing and rail validation: " + ", ".join(rail_names))
        for group in cls._detect_interface_groups(text)[:10]:
            name = group["name"]
            if name == "Protection/ESD":
                focus.append("Protection device continuity and clamp orientation review")
            elif name == "Wireless/SIM":
                focus.append("SIM/LTE modem power, UART, USB, reset, and enable-line verification")
            elif name == "USB":
                focus.append("USB host/hub differential-pair continuity and VBUS current-limit validation")
            elif name == "Ethernet":
                focus.append("Ethernet magnetics, MDI pair mapping, LEDs, and shield grounding checks")
            elif name == "HDMI":
                focus.append("HDMI hotplug, DDC, 5 V switch, and high-speed pair continuity checks")
            elif name == "RS485":
                focus.append("RS485 A/B line polarity, termination, TVS, and direction-control checks")
            else:
                focus.append(f"{name} interface continuity and functional smoke test")
        return focus[:14]

    @classmethod
    def _build_risk_flags(cls, text: str, nets: list[str]) -> list[str]:
        flags = []
        lower = text.lower()
        if "usb" in lower or "hdmi" in lower or "pcie" in lower or "trd" in lower:
            flags.append("High-speed differential routing requires impedance, length-match, and ESD review.")
        if "sim" in lower or "gnss" in lower or "antenna" in lower:
            flags.append("Wireless/SIM section requires RF, carrier, antenna, and certification evidence before release.")
        if any("12V" in net or "VBAT" in net for net in nets):
            flags.append("Mixed-voltage rails require power sequencing and over-current validation.")
        if "rs485" in lower:
            flags.append("RS485 field wiring requires surge/ESD, termination, and isolation/grounding review.")
        if "cr2032" in lower:
            flags.append("Coin-cell RTC backup requires battery polarity, leakage, and serviceability checks.")
        if "fan" in lower:
            flags.append("Fan output requires load current, tachometer, and fault-condition validation.")
        return flags[:10]

    @staticmethod
    def _build_optimization_actions(
        text: str,
        power_rails: list[dict[str, str]],
        interface_groups: list[dict[str, Any]],
        component_counts: dict[str, int],
        risk_flags: list[str],
    ) -> list[dict[str, str]]:
        group_names = {group.get("name") for group in interface_groups}
        actions: list[dict[str, str]] = []

        def add(priority: str, area: str, recommendation: str, why: str, evidence: str) -> None:
            actions.append(
                {
                    "priority": priority,
                    "area": area,
                    "recommendation": recommendation,
                    "why": why,
                    "evidence": evidence,
                }
            )

        if power_rails:
            add(
                "P1",
                "Power integrity",
                "Build a measured rail budget with no-load, boot, peripheral-load, and fault-current rows.",
                "This converts rail names into evidence that can be used for release decisions and customer ratings.",
                ", ".join(rail["net"] for rail in power_rails[:6]),
            )
        else:
            add(
                "P1",
                "Power evidence",
                "Add explicit input and regulator net labels before generating customer manuals.",
                "The engine cannot produce a safe bring-up plan without named voltage domains.",
                "No named rails detected",
            )

        if {"USB", "HDMI", "PCIe", "Ethernet"} & group_names:
            add(
                "P1",
                "High-speed interfaces",
                "Add impedance, length-match, pair polarity, and ESD review checkpoints to the release checklist.",
                "High-speed connectors are frequent sources of hidden board-spin risk.",
                ", ".join(sorted({"USB", "HDMI", "PCIe", "Ethernet"} & group_names)),
            )

        if "Wireless/SIM" in group_names:
            add(
                "P1",
                "Wireless readiness",
                "Separate modem power, SIM, antenna, RF exposure, and carrier-certification evidence into their own release gate.",
                "Wireless sections need more proof than schematic connectivity before field deployment.",
                "Wireless/SIM evidence detected",
            )

        if {"RS485", "CAN/Fieldbus"} & group_names:
            add(
                "P2",
                "Field wiring robustness",
                "Document polarity, termination, biasing, isolation/ground strategy, and surge/ESD validation.",
                "Field wiring failures often come from installation variation rather than firmware behavior.",
                ", ".join(sorted({"RS485", "CAN/Fieldbus"} & group_names)),
            )

        if "Protection/ESD" in group_names or risk_flags:
            add(
                "P2",
                "Protection network",
                "Add a protection-device table with location, protected pins, clamp direction, and test evidence.",
                "Protection parts are easy to list but need orientation and placement validation.",
                "ESD/protection or risk flags detected",
            )

        if component_counts.get("integrated_circuits", 0) or component_counts.get("connectors_headers", 0):
            add(
                "P2",
                "BOM traceability",
                "Reconcile extracted IC and connector references against the native CAD BOM before procurement or release.",
                "PDF text extraction is a strong review seed, not a manufacturing BOM authority.",
                f"{component_counts.get('integrated_circuits', 0)} ICs, {component_counts.get('connectors_headers', 0)} connectors",
            )

        if "Debug/Programming" in group_names:
            add(
                "P3",
                "Service workflow",
                "Publish a recovery and programming procedure covering boot mode, reset, debug headers, and expected LED states.",
                "A product-like app/manual needs a clear recovery path for support teams.",
                "Debug/programming signals detected",
            )

        if "Fan" in group_names:
            add(
                "P3",
                "Thermal control",
                "Add fan current, tachometer, stalled-fan, and enclosure airflow validation to the test pack.",
                "Thermal accessories can change current draw, acoustics, and product reliability.",
                "Fan control evidence detected",
            )

        if not actions:
            add(
                "P2",
                "Evidence quality",
                "Upload schematic PDFs, BOM exports, and firmware pin maps before producing a release-grade document.",
                "The engine becomes much stronger as source evidence coverage improves.",
                "Limited evidence detected",
            )

        return actions[:12]

    @staticmethod
    def _build_validation_matrix(
        interface_groups: list[dict[str, Any]],
        power_rails: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        matrix: list[dict[str, str]] = []
        for rail in power_rails[:6]:
            matrix.append(
                {
                    "subsystem": rail.get("net", "Power rail"),
                    "objective": "Confirm safe power availability",
                    "method": "Measure voltage, ramp, current draw, ripple, and thermal behavior.",
                    "acceptance": "Within rated tolerance with no abnormal heating or current limiting.",
                }
            )

        validation_notes = {
            "USB": ("Confirm USB data and power path", "Check VBUS, D+/D- continuity, reset, enumeration, and current limiting.", "Known-good device enumerates without VBUS sag."),
            "HDMI": ("Confirm display interface", "Check HDMI 5 V, hotplug, DDC, CEC, and video detection.", "Display is detected repeatedly with a known-good cable."),
            "Ethernet": ("Confirm wired networking", "Check MDI pair continuity, magnetics, LEDs, link negotiation, and packet transfer.", "Stable link and data transfer across reboot cycles."),
            "Wireless/SIM": ("Confirm modem and SIM path", "Check modem rails, enable/reset, SIM voltage, UART/USB, antenna, and registration evidence.", "Module responds and reaches the intended network test state."),
            "RS485": ("Confirm field bus operation", "Check A/B polarity, termination, biasing, DE/RE timing, TVS, and loopback.", "Loopback and field device communication pass without bus contention."),
            "CAN/Fieldbus": ("Confirm field bus operation", "Check CANH/CANL polarity, termination, transceiver supply, and loopback traffic.", "Bus frames transmit and receive at the target bitrate."),
            "RTC": ("Confirm time retention", "Check backup voltage, crystal start, I2C access, and retention after power removal.", "Time is retained for the required service interval."),
            "Fan": ("Confirm thermal output", "Check fan voltage, current, tachometer feedback, PWM/control, and stalled-fan response.", "Fan speed feedback and fault behavior match requirements."),
            "GPIO Header": ("Confirm expansion safety", "Measure idle voltage, direction, pull state, and firmware mapping for each exposed pin.", "Pins match the published connector table."),
            "Protection/ESD": ("Confirm protection readiness", "Review clamp direction, protected nets, continuity, leakage, and pre-compliance evidence.", "Protection parts are correctly oriented and do not load active signals."),
        }

        for group in interface_groups:
            name = group.get("name", "Subsystem")
            objective, method, acceptance = validation_notes.get(
                name,
                (
                    "Confirm subsystem function",
                    "Run continuity, voltage, firmware, and smoke checks against the schematic evidence.",
                    "Measured behavior matches the intended product function.",
                ),
            )
            matrix.append(
                {
                    "subsystem": name,
                    "objective": objective,
                    "method": method,
                    "acceptance": acceptance,
                }
            )
        return matrix[:18]

    @staticmethod
    def _build_bringup_sequence(
        power_rails: list[dict[str, str]],
        interface_groups: list[dict[str, Any]],
    ) -> list[str]:
        group_names = {group.get("name") for group in interface_groups}
        sequence = [
            "Perform visual inspection for solder bridges, missing parts, connector damage, and board revision mismatch.",
            "Power the board with a current-limited supply and no external peripherals attached.",
        ]
        if power_rails:
            sequence.append("Verify base rails in order: " + ", ".join(rail["net"] for rail in power_rails[:8]) + ".")
        sequence.append("Confirm reset, enable, boot-mode, and status indicator behavior before interface testing.")
        ordered_groups = ["USB", "HDMI", "Ethernet", "RTC", "Fan", "Wireless/SIM", "RS485", "CAN/Fieldbus", "GPIO Header"]
        for name in ordered_groups:
            if name in group_names:
                sequence.append(f"Attach and validate the {name} block after base power is stable.")
        sequence.append("Record measurements, screenshots/logs, board revision, firmware version, and test operator.")
        return sequence[:14]

    @staticmethod
    def _calculate_readiness_score(
        power_rails: list[dict[str, str]],
        interface_groups: list[dict[str, Any]],
        key_parts: list[dict[str, str]],
        risk_flags: list[str],
        validation_matrix: list[dict[str, str]],
        skill_review_gates: list[dict[str, Any]],
    ) -> int:
        score = 35
        score += min(20, len(power_rails) * 3)
        score += min(25, len(interface_groups) * 2)
        score += min(10, len(key_parts))
        score += min(10, len(validation_matrix))
        score += min(10, len(skill_review_gates))
        score -= min(20, len(risk_flags) * 3)
        return max(0, min(100, score))

    @staticmethod
    def _extract_net_tokens(text: str) -> list[str]:
        net_pattern = re.compile(
            r"(?<![A-Za-z0-9_+.])(?:GND|VIN|VBAT|VDC_IN|\+?\d+(?:V|V\d)|\dV\d|[A-Z][A-Z0-9_]*(?:_[A-Z0-9]+)+)(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        priority = []
        seen: set[str] = set()
        for match in net_pattern.finditer(text):
            net = match.group(0)
            if net not in seen:
                priority.append(net)
                seen.add(net)
        return priority[:500]

    @staticmethod
    def _looks_like_signal_token(token: str) -> bool:
        return bool(
            re.fullmatch(r"D\d+[NP]", token)
            or re.fullmatch(r"D[MP]\d+", token)
            or re.fullmatch(r"[A-Z]+D\d+[NP]", token)
        )

    @staticmethod
    def _extract_document_dates(text: str) -> dict[str, str]:
        created = re.search(r"Create at\s+(\d{4}-\d{2}-\d{2})", text)
        updated = re.search(r"Update at\s+(\d{4}-\d{2}-\d{2})", text)
        return {
            "created": created.group(1) if created else "not provided",
            "updated": updated.group(1) if updated else "not provided",
        }

    @staticmethod
    def _compact_text(text: str, limit: int) -> str:
        compacted = re.sub(r"\s+", " ", text).strip()
        return compacted[:limit]

    def _list_files(self, directory: Path, extensions: set[str]) -> list[Path]:
        if not directory.exists():
            LOGGER.warning("Input directory does not exist: %s", directory)
            return []
        files = [
            path
            for path in directory.rglob("*")
            if path.is_file()
            and path.suffix.lower() in extensions
            and not path.name.startswith(".")
            and self._is_safe_scan_size(path)
        ]
        if not files:
            LOGGER.debug("No supported files found in %s", directory)
        if len(files) > self.MAX_SCAN_FILES:
            LOGGER.warning("Too many supported files in %s; scanning first %s.", directory, self.MAX_SCAN_FILES)
        return sorted(files)[: self.MAX_SCAN_FILES]

    def _is_safe_scan_size(self, path: Path) -> bool:
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size > self.MAX_SCAN_BYTES:
            LOGGER.warning("Skipping oversized input file %s (%s bytes).", path, size)
            return False
        return True

    @staticmethod
    def _strip_namespace(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
